from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "event_id",
    "event_type",
    "release_time",
    "available_time",
    "actual",
    "consensus",
}

OPTIONAL_NUMERIC_COLUMNS = [
    "previous",
    "revised_previous",
    "us2y_1m_bp",
    "us2y_5m_bp",
    "us2y_30m_bp",
    "us2y_60m_bp",
    "fed_reprice_5m_bp",
    "fed_reprice_30m_bp",
    "fed_reprice_next_bp",
    "fed_reprice_3m_bp",
    "fed_reprice_year_end_bp",
    "nq_5m_ret",
    "soxx_5m_ret",
    "dxy_5m_ret",
    "gold_5m_ret",
    "btc_5m_ret",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build PIT-safe Kalman Macro Event V1 features")
    p.add_argument("--events", required=True, help="CSV or parquet normalized macro calendar")
    p.add_argument("--spec", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def _load_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported event file: {path}")


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _expanding_prior_std(series: pd.Series, min_history: int) -> pd.Series:
    # Anti-leakage: the current release never contributes to its own scale.
    return series.shift(1).expanding(min_periods=min_history).std(ddof=1)


def build_event_features(events: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS.difference(events.columns)
    if missing:
        raise ValueError(f"macro event input missing columns: {sorted(missing)}")

    x = events.copy()
    x["event_id"] = x["event_id"].astype(str)
    x["event_type"] = x["event_type"].astype(str).str.upper().str.strip()
    x["release_time"] = _utc(x["release_time"])
    x["available_time"] = _utc(x["available_time"])
    if x[["release_time", "available_time"]].isna().any().any():
        raise ValueError("release_time/available_time must be parseable UTC timestamps")
    if (x["available_time"] < x["release_time"]).any():
        raise ValueError("available_time earlier than release_time")
    if x["event_id"].duplicated().any():
        raise ValueError("event_id must be unique")

    x["actual"] = _safe_numeric(x["actual"])
    x["consensus"] = _safe_numeric(x["consensus"])
    for col in OPTIONAL_NUMERIC_COLUMNS:
        if col in x.columns:
            x[col] = _safe_numeric(x[col])
        else:
            x[col] = np.nan

    definitions = {str(k).upper(): v for k, v in spec["event_definitions"].items()}
    unsupported = sorted(set(x["event_type"]) - set(definitions))
    if unsupported:
        raise ValueError(f"unsupported event_type values: {unsupported}")

    x["category"] = x["event_type"].map(
        lambda k: str(definitions[k]["category"]).upper()
    )
    x["hawkish_sign"] = x["event_type"].map(
        lambda k: float(definitions[k]["hawkish_sign"])
    )
    x["half_life_hours"] = x["event_type"].map(
        lambda k: float(definitions[k]["half_life_hours"])
    )

    x["surprise_raw"] = x["actual"] - x["consensus"]
    x["revision_raw"] = x["revised_previous"] - x["previous"]
    x = x.sort_values(["event_type", "available_time", "event_id"]).reset_index(drop=True)

    min_history = int(spec.get("surprise_z_min_history", 12))
    x["surprise_scale_prior"] = (
        x.groupby("event_type", group_keys=False)["surprise_raw"]
        .apply(lambda s: _expanding_prior_std(s, min_history))
        .reset_index(level=0, drop=True)
    )
    x["surprise_z"] = x["surprise_raw"] / x["surprise_scale_prior"].replace(0, np.nan)
    clip = float(spec.get("surprise_z_clip", 6.0))
    x["surprise_z"] = x["surprise_z"].clip(-clip, clip)
    x["hawkish_surprise_z"] = x["hawkish_sign"] * x["surprise_z"]

    direction = np.sign(x["hawkish_surprise_z"])
    x["rates_confirmation_30m_bp"] = direction * x["us2y_30m_bp"]
    x["policy_confirmation_30m_bp"] = direction * x["fed_reprice_30m_bp"]
    x["policy_confirmation_next_bp"] = direction * x["fed_reprice_next_bp"]

    x["has_consensus"] = x["consensus"].notna().astype(int)
    x["has_us2y_reaction"] = x["us2y_30m_bp"].notna().astype(int)
    x["has_fed_repricing"] = x["fed_reprice_30m_bp"].notna().astype(int)
    x["feature_version"] = str(spec["version"])
    return x.sort_values(["available_time", "event_id"]).reset_index(drop=True)


def main() -> int:
    args = parse_args()
    events_path = Path(args.events).expanduser()
    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out = build_event_features(_load_frame(events_path), spec)
    out.to_parquet(out_path, index=False)

    status = {
        "status": "READY",
        "version": spec["version"],
        "rows": int(len(out)),
        "min_available_time": out["available_time"].min(),
        "max_available_time": out["available_time"].max(),
        "event_types": sorted(out["event_type"].unique().tolist()),
        "categories": sorted(out["category"].unique().tolist()),
        "consensus_coverage": float(out["consensus"].notna().mean()),
        "us2y_30m_coverage": float(out["us2y_30m_bp"].notna().mean()),
        "fed_reprice_30m_coverage": float(out["fed_reprice_30m_bp"].notna().mean()),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    out_path.with_suffix(".status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
