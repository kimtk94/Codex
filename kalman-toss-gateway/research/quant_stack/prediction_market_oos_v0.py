from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.quant_stack.prediction_market_leadlag_v0 import (
    align_asset,
    build_event_hours,
    load_asset_history,
)
from research.quant_stack.prediction_market_stratified_v0 import summarize_group


def load_spec(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    spec = json.loads(raw.decode("utf-8"))
    return spec, hashlib.sha256(raw).hexdigest()


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("UTC") if pd.Timestamp(value).tzinfo else pd.Timestamp(value, tz="UTC")


def filter_strict_oos(prediction: pd.DataFrame, discovery_end_utc: str) -> pd.DataFrame:
    if "ts" not in prediction.columns:
        raise ValueError("prediction table requires ts")
    out = prediction.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out = out.dropna(subset=["ts"])
    cutoff = _utc(discovery_end_utc)
    return out[out["ts"] > cutoff].copy()


def evaluate_frozen_hypothesis(
    prediction: pd.DataFrame,
    asset: pd.DataFrame,
    spec: dict[str, Any],
    *,
    bootstrap_iterations: int = 5000,
) -> tuple[dict[str, Any], pd.DataFrame]:
    discovery = spec["discovery"]
    hypothesis = spec["hypothesis"]
    gate = spec["confirmatory_gate"]

    oos_prediction = filter_strict_oos(prediction, discovery["data_end_utc"])
    asset = asset.copy()
    asset["ts"] = pd.to_datetime(asset["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    asset = asset.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)

    threshold = float(hypothesis["shock_threshold"])
    channel = str(hypothesis["dominant_channel"])
    horizon = int(hypothesis["horizon_bars"])
    max_lag = float(hypothesis["max_entry_lag_minutes"])

    if oos_prediction.empty:
        return {
            "status": "WAITING_FOR_OOS_DATA",
            "reason": "no prediction rows exist strictly after discovery cutoff",
            "prediction_rows_after_cutoff": 0,
            "production_promotion": False,
            "r51_mutated": False,
        }, pd.DataFrame()

    events = build_event_hours(oos_prediction, min_abs_delta_1h=threshold)
    events = events[events["dominant_channel"] == channel].copy()
    if events.empty:
        return {
            "status": "WAITING_FOR_OOS_EVENTS",
            "reason": "OOS rows exist but no frozen-hypothesis events meet the threshold/channel",
            "prediction_rows_after_cutoff": int(len(oos_prediction)),
            "event_rows": 0,
            "production_promotion": False,
            "r51_mutated": False,
        }, pd.DataFrame()

    aligned = align_asset(events, asset)
    aligned = aligned[
        aligned["entry_lag_minutes"].notna()
        & (aligned["entry_lag_minutes"] <= max_lag)
    ].copy()

    ret_col = f"fwd_return_{horizon}bar"
    if ret_col not in aligned.columns:
        raise ValueError(f"asset history missing {ret_col}")

    valid = aligned[aligned[ret_col].notna()].copy()
    if valid.empty:
        return {
            "status": "WAITING_FOR_ASSET_OUTCOMES",
            "reason": "frozen events exist but the requested forward asset horizon is unavailable",
            "prediction_rows_after_cutoff": int(len(oos_prediction)),
            "event_rows": int(len(events)),
            "aligned_rows": int(len(aligned)),
            "production_promotion": False,
            "r51_mutated": False,
        }, aligned

    summary = summarize_group(
        valid,
        threshold=threshold,
        symbol=str(hypothesis["symbol"]),
        group_type="FROZEN_OOS",
        group_name=channel,
        bootstrap_iterations=bootstrap_iterations,
    )
    selected = [row for row in summary if int(row["bars"]) == horizon]
    if len(selected) != 1:
        raise RuntimeError(f"expected one horizon row, got {len(selected)}")
    metrics = selected[0]

    checks = {
        "n_min": int(metrics["n"]) >= int(gate["n_min"]),
        "unique_dates_min": int(metrics["unique_dates"]) >= int(gate["unique_dates_min"]),
        "hit_rate_min": float(metrics["hit_rate"]) >= float(gate["hit_rate_min"]),
        "positive_date_rate_min": (
            metrics["positive_date_rate"] is not None
            and float(metrics["positive_date_rate"]) >= float(gate["positive_date_rate_min"])
        ),
        "mean_signed_return_gt": float(metrics["mean_signed_return"]) > float(gate["mean_signed_return_gt"]),
        "cluster_bootstrap_ci_low_gt": (
            metrics["bootstrap_ci_low"] is not None
            and float(metrics["bootstrap_ci_low"]) > float(gate["cluster_bootstrap_ci_low_gt"])
        ),
        "cluster_signflip_p_max": (
            metrics["cluster_signflip_p"] is not None
            and float(metrics["cluster_signflip_p"]) <= float(gate["cluster_signflip_p_max"])
        ),
    }

    sample_ready = checks["n_min"] and checks["unique_dates_min"]
    if not sample_ready:
        status = "INSUFFICIENT_OOS_SAMPLE"
    elif all(checks.values()):
        status = "PASS_CONFIRMATORY_GATE"
    else:
        status = "FAIL_CONFIRMATORY_GATE"

    payload = {
        "status": status,
        "hypothesis_id": spec["hypothesis_id"],
        "prediction_rows_after_cutoff": int(len(oos_prediction)),
        "event_rows": int(len(events)),
        "aligned_rows": int(len(aligned)),
        "valid_horizon_rows": int(len(valid)),
        "metrics": metrics,
        "gate_checks": checks,
        "confirmatory_gate": gate,
        "production_promotion": False,
        "r51_mutated": False,
        "auto_promote": False,
    }
    return payload, valid


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Frozen prediction-market OOS evaluator v0")
    p.add_argument("--prediction", required=True)
    p.add_argument("--asset", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--bootstrap-iterations", type=int, default=5000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec)
    spec, spec_sha256 = load_spec(spec_path)
    prediction = pd.read_parquet(args.prediction)
    symbol = str(spec["hypothesis"]["symbol"])
    asset = load_asset_history(Path(args.asset), symbol)

    payload, rows = evaluate_frozen_hypothesis(
        prediction,
        asset,
        spec,
        bootstrap_iterations=args.bootstrap_iterations,
    )

    payload["spec_sha256"] = spec_sha256
    payload["frozen_at_utc"] = spec["frozen_at_utc"]
    payload["discovery_data_end_utc"] = spec["discovery"]["data_end_utc"]
    payload["hypothesis"] = spec["hypothesis"]
    payload["safety"] = spec["safety"]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "oos_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    if not rows.empty:
        rows.to_parquet(out_dir / "oos_aligned_rows.parquet", index=False)

    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
