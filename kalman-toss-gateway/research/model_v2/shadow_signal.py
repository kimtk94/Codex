from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .model_contract import score_row


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Score Kalman V2 JSON models into file-only SHADOW signals")
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-missing-feature-ratio", type=float, default=0.15)
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def deterministic_run_id(
    *,
    strategy_version: str,
    market: str,
    symbol: str,
    as_of: str,
    model_sha256: str,
) -> str:
    source = "|".join([strategy_version, market, symbol, as_of, model_sha256])
    return "v2-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def build_shadow_signal(
    *,
    market_name: str,
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
    model_sha256: str,
    max_missing_feature_ratio: float,
) -> dict[str, Any]:
    if matrix.empty:
        raise RuntimeError(f"{market_name}: empty feature matrix")

    matrix = matrix.copy()
    matrix["as_of"] = pd.to_datetime(matrix["as_of"], errors="raise")
    latest = matrix.sort_values("as_of").iloc[-1]
    score = score_row(latest, artifact)

    as_of = pd.Timestamp(latest["as_of"])
    if as_of.tzinfo is None:
        as_of_utc = as_of.tz_localize("UTC")
    else:
        as_of_utc = as_of.tz_convert("UTC")
    as_of_iso = as_of_utc.isoformat()

    trained_through = pd.Timestamp(artifact["training_window"]["refit_through"])
    if trained_through.tzinfo is None:
        trained_through = trained_through.tz_localize("UTC")
    else:
        trained_through = trained_through.tz_convert("UTC")

    missing_ok = score["missing_feature_ratio"] <= max_missing_feature_ratio
    probability = float(score["probability_up"])
    threshold = float(score["probability_threshold"])
    probability_ok = math.isfinite(probability)
    shadow_entry = bool(score["shadow_entry"] and missing_ok and probability_ok)

    if not probability_ok:
        quality = "FAIL"
        risk_gate = "DATA_QUALITY_FAIL"
    elif not missing_ok:
        quality = "DEGRADED"
        risk_gate = "DATA_QUALITY_FAIL"
    else:
        quality = "PASS"
        risk_gate = "SHADOW_ONLY"

    strategy_version = str(artifact["strategy_version"])
    symbol = str(artifact["symbol"])
    run_id = deterministic_run_id(
        strategy_version=strategy_version,
        market=market_name,
        symbol=symbol,
        as_of=as_of_iso,
        model_sha256=model_sha256,
    )

    return {
        "run_id": run_id,
        "market": market_name,
        "symbol": symbol,
        "as_of": as_of_iso,
        "strategy_version": strategy_version,
        "signal": "SHADOW",
        "entry_allowed": False,
        "risk_gate": risk_gate,
        "position_state": "FLAT",
        "payload": {
            "model_version": artifact["model_version"],
            "dataset_version": artifact["dataset_version"],
            "feature_set": artifact["feature_set"],
            "model_family": artifact["model_family"],
            "model_sha256": model_sha256,
            "probability_up": probability,
            "probability_threshold": threshold,
            "shadow_direction": "BUY" if shadow_entry else "WATCH",
            "shadow_entry_this_signal": shadow_entry,
            "selected_feature_count": score["selected_feature_count"],
            "missing_feature_count": score["missing_feature_count"],
            "missing_feature_ratio": score["missing_feature_ratio"],
            "max_missing_feature_ratio": max_missing_feature_ratio,
            "data_quality": quality,
            "is_forward_shadow": bool(as_of_utc > trained_through),
            "trained_through": trained_through.isoformat(),
            "horizon_observations": artifact["horizon_observations"],
            "allow_trade_shadow": False,
            "live_execution": False,
            "production_promotion": False,
            "neon_write": False,
        },
    }


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    model_dir = Path(args.model_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))

    signals: list[dict[str, Any]] = []
    status: dict[str, Any] = {
        "status": "READY",
        "model_version": spec["version"],
        "shadow_only": True,
        "neon_write": False,
        "live_execution": False,
        "markets": {},
    }

    for market_name in spec["markets"]:
        try:
            matrix_path = matrix_dir / f"{market_name.lower()}_matrix.parquet"
            model_path = model_dir / market_name.lower() / "model.json"
            if not matrix_path.exists():
                raise FileNotFoundError(matrix_path)
            if not model_path.exists():
                raise FileNotFoundError(model_path)

            matrix = pd.read_parquet(matrix_path)
            artifact = json.loads(model_path.read_text(encoding="utf-8"))
            model_sha = sha256_file(model_path)
            signal = build_shadow_signal(
                market_name=market_name,
                matrix=matrix,
                artifact=artifact,
                model_sha256=model_sha,
                max_missing_feature_ratio=float(args.max_missing_feature_ratio),
            )
            signals.append(signal)

            date_key = pd.Timestamp(signal["as_of"]).strftime("%Y-%m-%d")
            atomic_json(
                output_dir / "history" / date_key / f"{market_name.lower()}.json",
                signal,
            )
            atomic_json(
                output_dir / "latest" / f"{market_name.lower()}.json",
                signal,
            )
            status["markets"][market_name] = {
                "status": "READY",
                "run_id": signal["run_id"],
                "as_of": signal["as_of"],
                "shadow_direction": signal["payload"]["shadow_direction"],
                "probability_up": signal["payload"]["probability_up"],
                "data_quality": signal["payload"]["data_quality"],
                "is_forward_shadow": signal["payload"]["is_forward_shadow"],
            }
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market_name] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    atomic_json(output_dir / "latest" / "shadow_signals.json", signals)
    atomic_json(output_dir / "shadow_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
