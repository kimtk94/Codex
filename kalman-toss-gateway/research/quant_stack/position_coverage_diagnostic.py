from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from research.quant_stack.live_policy_replay import (
    NY,
    KST,
    ReplayPolicyConfig,
    replay_one_trade,
)
from research.quant_stack.open_revalidation_backtest import _write_json


def _cfg_from_snapshot(path: Path) -> ReplayPolicyConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    p = raw.get("policy") or {}
    return ReplayPolicyConfig(
        profit_flip_enabled=bool(p["profit_flip_enabled"]),
        arm_pct=Decimal(str(p["arm_pct"])),
        trigger_pct=Decimal(str(p["trigger_pct"])),
        recovery_pct=Decimal(str(p["recovery_pct"])),
        confirm_observations=int(p["confirm_observations"]),
        stop_loss=Decimal(str(p["stop_loss"])),
        take_profit=Decimal(str(p["take_profit"])),
        model_rotation_enabled=bool(p["model_rotation_enabled"]),
        target_exit_buckets=int(p.get("target_exit_buckets", 4)),
    )


def _session_bucket(ts: pd.Timestamp) -> str:
    local = ts.tz_convert(NY)
    minute = local.hour * 60 + local.minute
    if minute >= 20 * 60 or minute < 4 * 60:
        return "OVERNIGHT_20_04"
    if minute < 9 * 60 + 30:
        return "PREMARKET_04_0930"
    if minute < 16 * 60:
        return "REGULAR_0930_16"
    return "POSTMARKET_16_20"


def _prior_boats(
    bars: pd.DataFrame,
    ts: pd.Timestamp,
) -> tuple[pd.Timestamp | None, float | None]:
    if "source_feed" not in bars.columns or "timestamp" not in bars.columns:
        return None, None
    z = bars.loc[
        bars["source_feed"].fillna("").astype(str).eq("boats")
    ].copy()
    if z.empty:
        return None, None
    z["timestamp"] = pd.to_datetime(z["timestamp"], utc=True, errors="coerce")
    z = z.loc[z["timestamp"].notna() & (z["timestamp"] < ts)]
    if z.empty:
        return None, None
    last = z.sort_values("timestamp").iloc[-1]
    last_ts = pd.Timestamp(last["timestamp"])
    age_min = (ts - last_ts).total_seconds() / 60.0
    return last_ts, float(age_min)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnose missing POSITION_WATCH coverage from cached replay bars only."
    )
    p.add_argument(
        "--audit",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/live_policy_replay_v1_2025_full/live_policy_replay_trade_audit.parquet",
    )
    p.add_argument(
        "--policy-snapshot",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/live_policy_replay_v1_2025_full/policy_snapshot.json",
    )
    p.add_argument(
        "--output",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/live_policy_replay_v1_2025_full/position_coverage_diagnostic.json",
    )
    p.add_argument("--primary-feed", default="iex")
    p.add_argument("--overnight-feed", default="boats")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    audit_path = Path(args.audit)
    snapshot_path = Path(args.policy_snapshot)

    if not audit_path.is_file():
        raise FileNotFoundError(audit_path)
    if not snapshot_path.is_file():
        raise FileNotFoundError(snapshot_path)

    audit = pd.read_parquet(audit_path)
    cfg = _cfg_from_snapshot(snapshot_path)

    missing_by_bucket: Counter[str] = Counter()
    missing_by_et_hour: Counter[str] = Counter()
    missing_by_kst_hour: Counter[str] = Counter()
    missing_by_symbol: Counter[str] = Counter()
    prior_boats_ages: list[float] = []
    prior_boats_available = 0
    missing_position_events = 0
    evaluated_position_events = 0
    low_coverage_rows = 0
    cache_missing = 0
    unready_rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for _, row in audit.iterrows():
        if not bool(row.get("replay_data_ready", False)):
            unready_rows.append(
                {
                    "symbol": row.get("symbol"),
                    "entry_timestamp": row.get("entry_timestamp"),
                    "exit_timestamp": row.get("exit_timestamp"),
                    "replay_error": row.get("replay_error"),
                    "cache_path": row.get("cache_path"),
                }
            )
            continue

        position_cov = pd.to_numeric(
            pd.Series([row.get("position_watch_coverage")]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(position_cov) or float(position_cov) >= 1.0:
            continue

        low_coverage_rows += 1
        cache_path = Path(str(row.get("cache_path") or ""))
        if not cache_path.is_file():
            cache_missing += 1
            continue

        bars = pd.read_parquet(cache_path)
        _, events = replay_one_trade(
            row,
            bars=bars,
            config=cfg,
            event_audit="full",
            primary_feed=args.primary_feed,
            overnight_feed=args.overnight_feed,
        )

        symbol = str(row.get("symbol") or "")
        for event in events:
            if event.get("source") != "POSITION_WATCH":
                continue

            evaluated_position_events += 1
            if bool(event.get("price_available")):
                continue

            missing_position_events += 1
            ts = pd.Timestamp(event["timestamp"])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")

            et = ts.tz_convert(NY)
            kst = ts.tz_convert(KST)
            bucket = _session_bucket(ts)

            missing_by_bucket[bucket] += 1
            missing_by_et_hour[f"{et.hour:02d}"] += 1
            missing_by_kst_hour[f"{kst.hour:02d}"] += 1
            missing_by_symbol[symbol] += 1

            prior_ts, prior_age = _prior_boats(bars, ts)
            if prior_ts is not None and prior_age is not None:
                prior_boats_available += 1
                prior_boats_ages.append(prior_age)

            if len(samples) < 30:
                samples.append(
                    {
                        "symbol": symbol,
                        "timestamp_utc": ts,
                        "timestamp_et": et,
                        "timestamp_kst": kst,
                        "session_bucket": bucket,
                        "prior_boats_timestamp_utc": prior_ts,
                        "prior_boats_age_minutes": prior_age,
                    }
                )

    prior_ratio = (
        float(prior_boats_available / missing_position_events)
        if missing_position_events
        else None
    )

    carry_caps = [30, 60, 120, 180, 240, 360, 720, 1440]
    carry_sensitivity = []
    for cap in carry_caps:
        fillable = sum(1 for age in prior_boats_ages if age <= cap)
        carry_sensitivity.append(
            {
                "max_stale_minutes": cap,
                "fillable_missing_events": int(fillable),
                "fillable_missing_ratio": (
                    float(fillable / missing_position_events)
                    if missing_position_events
                    else None
                ),
                "remaining_missing_events": int(
                    max(0, missing_position_events - fillable)
                ),
            }
        )

    payload = {
        "schema": "kalman-live-policy-position-coverage-diagnostic-v1",
        "research_only": True,
        "production_changed": False,
        "automation_changed": False,
        "audit": str(audit_path),
        "rows": int(len(audit)),
        "low_position_coverage_rows": int(low_coverage_rows),
        "unready_rows": unready_rows,
        "cache_missing": int(cache_missing),
        "evaluated_position_events_in_low_coverage_rows": int(
            evaluated_position_events
        ),
        "missing_position_events": int(missing_position_events),
        "missing_by_session_bucket": dict(sorted(missing_by_bucket.items())),
        "missing_by_et_hour": dict(sorted(missing_by_et_hour.items())),
        "missing_by_kst_hour": dict(sorted(missing_by_kst_hour.items())),
        "top_missing_symbols": missing_by_symbol.most_common(20),
        "prior_boats_available_for_missing": int(prior_boats_available),
        "prior_boats_available_ratio": prior_ratio,
        "prior_boats_age_minutes_median": (
            None
            if not prior_boats_ages
            else float(pd.Series(prior_boats_ages).median())
        ),
        "prior_boats_age_minutes_p95": (
            None
            if not prior_boats_ages
            else float(pd.Series(prior_boats_ages).quantile(0.95))
        ),
        "carry_sensitivity": carry_sensitivity,
        "samples": samples,
    }

    if missing_position_events == 0:
        diagnosis = "NO_POSITION_WATCH_GAP_REPRODUCED"
    elif (
        missing_by_bucket.get("PREMARKET_04_0930", 0)
        == missing_position_events
        and prior_ratio is not None
        and prior_ratio >= 0.95
    ):
        diagnosis = "PREMARKET_SESSION_BOUNDARY_CARRY_CANDIDATE"
    elif missing_by_bucket.get("PREMARKET_04_0930", 0) >= 0.80 * missing_position_events:
        diagnosis = "PREMARKET_PRIMARY_FEED_SPARSITY"
    else:
        diagnosis = "MIXED_POSITION_WATCH_GAPS"

    payload["diagnosis"] = diagnosis

    _write_json(Path(args.output), payload)

    print("====================================================")
    print("POSITION WATCH COVERAGE DIAGNOSTIC")
    print("====================================================")
    print(f"rows={len(audit)}")
    print(f"low_position_coverage_rows={low_coverage_rows}")
    print(f"unready_rows={len(unready_rows)}")
    print(f"cache_missing={cache_missing}")
    print(f"missing_position_events={missing_position_events}")
    print(
        "missing_by_session_bucket="
        + json.dumps(payload["missing_by_session_bucket"], sort_keys=True)
    )
    print(
        "missing_by_et_hour="
        + json.dumps(payload["missing_by_et_hour"], sort_keys=True)
    )
    print(
        f"prior_boats_available_ratio={prior_ratio}"
    )
    print(
        "prior_boats_age_minutes_median="
        f"{payload['prior_boats_age_minutes_median']}"
    )
    print(
        "prior_boats_age_minutes_p95="
        f"{payload['prior_boats_age_minutes_p95']}"
    )
    print("carry_sensitivity=" + json.dumps(carry_sensitivity, sort_keys=True))
    print(f"diagnosis={diagnosis}")
    print(f"output={args.output}")

    if unready_rows:
        print()
        print("UNREADY_ROWS")
        for row in unready_rows:
            print(json.dumps(row, default=str, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
