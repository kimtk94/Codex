from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


ANCHORS = {
    "US": "US_SPY",
    "KR": "KR_KOSPI",
    "BTC": "BTC_BTCUSD",
}


def _ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def inspect_source_freshness(
    *,
    raw_path: Path,
    feature_path: Path,
    seed_end: pd.Timestamp,
) -> dict[str, Any]:
    seed = _ts(seed_end)
    if not raw_path.exists():
        raise FileNotFoundError(raw_path)
    if not feature_path.exists():
        raise FileNotFoundError(feature_path)

    raw = pd.read_parquet(
        raw_path,
        columns=["indicator_id", "event_time"],
    )
    features = pd.read_parquet(
        feature_path,
        columns=["indicator_id", "available_time"],
    )

    raw["event_time"] = pd.to_datetime(
        raw["event_time"], utc=True, errors="coerce"
    )
    features["available_time"] = pd.to_datetime(
        features["available_time"], utc=True, errors="coerce"
    )

    anchor_max: dict[str, str | None] = {}
    anchor_ready: dict[str, bool] = {}
    for market, indicator_id in ANCHORS.items():
        series = raw.loc[
            raw["indicator_id"].astype(str) == indicator_id,
            "event_time",
        ].dropna()
        latest = None if series.empty else pd.Timestamp(series.max())
        anchor_max[market] = None if latest is None else latest.isoformat()
        anchor_ready[market] = bool(
            latest is not None and latest > seed
        )

    feature_series = features["available_time"].dropna()
    feature_max = (
        None
        if feature_series.empty
        else pd.Timestamp(feature_series.max())
    )
    feature_ready = bool(
        feature_max is not None and feature_max > seed
    )

    ready = all(anchor_ready.values()) and feature_ready
    return {
        "status": "READY" if ready else "WAITING_SOURCE_REFRESH",
        "seed_end": seed.isoformat(),
        "anchor_max": anchor_max,
        "anchor_ready": anchor_ready,
        "feature_max_available_time": (
            None if feature_max is None else feature_max.isoformat()
        ),
        "feature_ready": feature_ready,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "production_write": False,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check whether historical integrated sources advanced beyond shadow seed"
    )
    p.add_argument("--raw", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--seed-end", required=True)
    p.add_argument("--output")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    payload = inspect_source_freshness(
        raw_path=Path(args.raw).expanduser(),
        feature_path=Path(args.features).expanduser(),
        seed_end=_ts(args.seed_end),
    )
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
