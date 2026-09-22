from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .model_contract import score_frame, score_row


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


def _utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _calibration_metrics(
    y_true: pd.Series,
    probability: pd.Series,
    *,
    bins: int = 10,
) -> dict[str, Any]:
    y = pd.to_numeric(y_true, errors="coerce").to_numpy(dtype=float)
    p = pd.to_numeric(probability, errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(y) & np.isfinite(p)
    y = y[finite]
    p = np.clip(p[finite], 1e-12, 1.0 - 1e-12)
    if len(y) == 0:
        return {"rows": 0}

    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))

    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.minimum(np.digitize(p, edges[1:-1], right=False), bins - 1)
    reliability: list[dict[str, Any]] = []
    ece = 0.0
    for idx in range(bins):
        mask = bucket == idx
        count = int(mask.sum())
        if count == 0:
            continue
        mean_p = float(np.mean(p[mask]))
        observed = float(np.mean(y[mask]))
        ece += (count / len(y)) * abs(mean_p - observed)
        reliability.append(
            {
                "bin": idx,
                "lower": float(edges[idx]),
                "upper": float(edges[idx + 1]),
                "rows": count,
                "mean_probability": mean_p,
                "observed_positive_rate": observed,
                "absolute_gap": abs(mean_p - observed),
            }
        )

    positive_rate = float(np.mean(y))
    baseline_brier = positive_rate * (1.0 - positive_rate)
    if 0.0 < positive_rate < 1.0:
        baseline_log_loss = float(
            -(
                positive_rate * np.log(positive_rate)
                + (1.0 - positive_rate) * np.log(1.0 - positive_rate)
            )
        )
    else:
        baseline_log_loss = 0.0

    return {
        "rows": int(len(y)),
        "positive_rate": positive_rate,
        "mean_probability": float(np.mean(p)),
        "brier": brier,
        "baseline_brier": baseline_brier,
        "brier_skill": (
            float(1.0 - brier / baseline_brier)
            if baseline_brier > 0
            else None
        ),
        "log_loss": logloss,
        "baseline_log_loss": baseline_log_loss,
        "log_loss_skill": (
            float(1.0 - logloss / baseline_log_loss)
            if baseline_log_loss > 0
            else None
        ),
        "ece_10bin": float(ece),
        "extreme_probability_rate": float(np.mean((p <= 0.01) | (p >= 0.99))),
        "reliability_bins": reliability,
    }


def model_quality_audit(
    artifact: dict[str, Any],
    quality_gate: dict[str, Any] | None = None,
    forward_calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = dict(quality_gate or {})
    minimum_rows = int(gate.get("minimum_test_rows", 100))
    minimum_auc = float(gate.get("minimum_test_roc_auc", 0.52))
    minimum_brier_skill = float(gate.get("minimum_brier_skill", 0.0))
    minimum_log_loss_skill = float(gate.get("minimum_log_loss_skill", 0.0))
    maximum_forward_ece = float(gate.get("maximum_forward_ece", 0.20))

    metrics = artifact.get("test_metrics") or {}
    rows = int(metrics.get("rows") or 0)
    positive_rate = metrics.get("positive_rate")
    auc = metrics.get("roc_auc")
    brier = metrics.get("brier")
    logloss = metrics.get("log_loss")

    try:
        p = float(positive_rate)
    except Exception:
        p = float("nan")
    try:
        auc_value = float(auc)
    except Exception:
        auc_value = float("nan")
    try:
        brier_value = float(brier)
    except Exception:
        brier_value = float("nan")
    try:
        logloss_value = float(logloss)
    except Exception:
        logloss_value = float("nan")

    baseline_brier = (
        p * (1.0 - p)
        if math.isfinite(p)
        else float("nan")
    )
    baseline_log_loss = (
        -(p * math.log(p) + (1.0 - p) * math.log(1.0 - p))
        if math.isfinite(p) and 0.0 < p < 1.0
        else float("nan")
    )
    brier_skill = (
        1.0 - brier_value / baseline_brier
        if math.isfinite(brier_value)
        and math.isfinite(baseline_brier)
        and baseline_brier > 0
        else float("nan")
    )
    log_loss_skill = (
        1.0 - logloss_value / baseline_log_loss
        if math.isfinite(logloss_value)
        and math.isfinite(baseline_log_loss)
        and baseline_log_loss > 0
        else float("nan")
    )

    checks: dict[str, bool] = {
        "minimum_test_rows": rows >= minimum_rows,
        "minimum_test_roc_auc": (
            math.isfinite(auc_value) and auc_value >= minimum_auc
        ),
        "minimum_brier_skill": (
            math.isfinite(brier_skill) and brier_skill >= minimum_brier_skill
        ),
        "minimum_log_loss_skill": (
            math.isfinite(log_loss_skill)
            and log_loss_skill >= minimum_log_loss_skill
        ),
    }

    forward_gate_applied = bool(
        forward_calibration
        and forward_calibration.get("sufficient_for_interpretation") is True
    )
    if forward_gate_applied:
        ece = forward_calibration.get("ece_10bin")
        try:
            ece_value = float(ece)
        except Exception:
            ece_value = float("nan")
        checks["maximum_forward_ece"] = (
            math.isfinite(ece_value) and ece_value <= maximum_forward_ece
        )

    passed = all(checks.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "thresholds": {
            "minimum_test_rows": minimum_rows,
            "minimum_test_roc_auc": minimum_auc,
            "minimum_brier_skill": minimum_brier_skill,
            "minimum_log_loss_skill": minimum_log_loss_skill,
            "maximum_forward_ece": maximum_forward_ece,
        },
        "test_rows": rows,
        "test_roc_auc": auc if auc is not None else None,
        "test_brier": brier if brier is not None else None,
        "baseline_brier": (
            baseline_brier if math.isfinite(baseline_brier) else None
        ),
        "brier_skill": brier_skill if math.isfinite(brier_skill) else None,
        "test_log_loss": logloss if logloss is not None else None,
        "baseline_log_loss": (
            baseline_log_loss if math.isfinite(baseline_log_loss) else None
        ),
        "log_loss_skill": (
            log_loss_skill if math.isfinite(log_loss_skill) else None
        ),
        "forward_gate_applied": forward_gate_applied,
    }


def forward_calibration_audit(
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
    *,
    minimum_rows: int = 20,
) -> dict[str, Any]:
    """Audit fixed-model calibration only on labels realized after held-out test_end."""
    window = artifact.get("training_window") or {}
    test_end_raw = window.get("test_end")
    if not test_end_raw:
        return {
            "status": "UNAVAILABLE",
            "reason": "model artifact missing training_window.test_end",
            "artifact_test_metrics": artifact.get("test_metrics"),
        }

    frame = matrix.copy()
    frame["as_of"] = pd.to_datetime(frame["as_of"], utc=True, errors="coerce")
    target = pd.to_numeric(frame.get("target_label"), errors="coerce")
    test_end = _utc_timestamp(test_end_raw)
    eligible = frame.loc[(frame["as_of"] > test_end) & target.notna()].copy()

    base = {
        "window": "POST_TEST_END_REALIZED_LABELS",
        "test_end": test_end.isoformat(),
        "minimum_rows_for_interpretation": int(minimum_rows),
        "artifact_test_metrics": artifact.get("test_metrics"),
    }
    if eligible.empty:
        return {
            "status": "WAITING_FOR_FORWARD_LABELS",
            "sufficient_for_interpretation": False,
            **base,
            "rows": 0,
        }

    scored = score_frame(eligible, artifact)
    metrics = _calibration_metrics(
        eligible["target_label"],
        scored["probability_up"],
    )
    rows = int(metrics.get("rows") or 0)
    return {
        "status": "READY" if rows >= minimum_rows else "TRACKING",
        "sufficient_for_interpretation": rows >= minimum_rows,
        **base,
        "first_as_of": eligible["as_of"].min().isoformat(),
        "last_as_of": eligible["as_of"].max().isoformat(),
        **metrics,
    }


def build_shadow_signal(
    *,
    market_name: str,
    matrix: pd.DataFrame,
    artifact: dict[str, Any],
    model_sha256: str,
    max_missing_feature_ratio: float,
    quality_gate: dict[str, Any] | None = None,
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

    gate = dict(quality_gate or {})
    forward_calibration = forward_calibration_audit(
        matrix,
        artifact,
        minimum_rows=int(gate.get("minimum_forward_calibration_rows", 20)),
    )
    model_quality = model_quality_audit(
        artifact,
        gate,
        forward_calibration,
    )
    model_quality_ok = model_quality["status"] == "PASS"

    raw_shadow_entry = bool(
        score["shadow_entry"] and missing_ok and probability_ok
    )
    shadow_entry = bool(raw_shadow_entry and model_quality_ok)

    if not probability_ok:
        quality = "FAIL"
        risk_gate = "DATA_QUALITY_FAIL"
    elif not missing_ok:
        quality = "DEGRADED"
        risk_gate = "DATA_QUALITY_FAIL"
    elif not model_quality_ok:
        quality = "PASS"
        risk_gate = "MODEL_QUALITY_FAIL"
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
            "probability_interpretation": "RAW_UNCALIBRATED_MODEL_SCORE",
            "raw_shadow_direction": "BUY" if raw_shadow_entry else "WATCH",
            "raw_shadow_entry_this_signal": raw_shadow_entry,
            "shadow_direction": "BUY" if shadow_entry else "WATCH",
            "shadow_entry_this_signal": shadow_entry,
            "model_quality": model_quality,
            "forward_calibration": forward_calibration,
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
                quality_gate=spec.get("shadow_quality_gate") or {},
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
                "raw_shadow_direction": signal["payload"]["raw_shadow_direction"],
                "shadow_direction": signal["payload"]["shadow_direction"],
                "risk_gate": signal["risk_gate"],
                "probability_up": signal["payload"]["probability_up"],
                "probability_interpretation": signal["payload"][
                    "probability_interpretation"
                ],
                "data_quality": signal["payload"]["data_quality"],
                "model_quality": signal["payload"]["model_quality"],
                "is_forward_shadow": signal["payload"]["is_forward_shadow"],
                "calibration": signal["payload"]["forward_calibration"],
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
