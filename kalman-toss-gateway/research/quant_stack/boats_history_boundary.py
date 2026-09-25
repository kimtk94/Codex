from __future__ import annotations

import argparse
import json
import os
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from research.quant_stack.open_revalidation_backtest import (
    _default_us_etf_root,
    _fetch_alpaca_1m,
    _write_json,
)

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
SCHEMA = "kalman-boats-history-boundary-v1"


def _month_start(value: pd.Timestamp) -> pd.Timestamp:
    x = pd.Timestamp(value)
    if x.tzinfo is None:
        x = x.tz_localize("UTC")
    else:
        x = x.tz_convert("UTC")
    return pd.Timestamp(datetime(x.year, x.month, 1, tzinfo=UTC))


def _next_month(value: pd.Timestamp) -> pd.Timestamp:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return pd.Timestamp(datetime(year, month, 1, tzinfo=UTC))


def _month_windows(start: Any, end: Any) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")

    cur = _month_start(start_ts)
    out: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    while cur < end_ts:
        nxt = _next_month(cur)
        left = max(cur, start_ts)
        right = min(nxt, end_ts)
        if left < right:
            out.append((left, right))
        cur = nxt
    return out


def _baseline_range(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "rows": 0,
            "fixed4_rows": 0,
            "entry_min_utc": None,
            "entry_max_utc": None,
            "exit_min_utc": None,
            "exit_max_utc": None,
        }

    frame = pd.read_parquet(path)
    if "policy" in frame.columns:
        frame = frame.loc[frame["policy"].astype(str) == "FIXED_4"].copy()

    for col in ("entry_timestamp", "exit_timestamp"):
        if col in frame.columns:
            frame[col] = pd.to_datetime(frame[col], utc=True, errors="coerce")

    entry = (
        frame["entry_timestamp"].dropna()
        if "entry_timestamp" in frame.columns
        else pd.Series(dtype="datetime64[ns, UTC]")
    )
    exit_ = (
        frame["exit_timestamp"].dropna()
        if "exit_timestamp" in frame.columns
        else pd.Series(dtype="datetime64[ns, UTC]")
    )

    return {
        "path": str(path),
        "exists": True,
        "rows": int(len(pd.read_parquet(path))),
        "fixed4_rows": int(len(frame)),
        "entry_min_utc": None if entry.empty else entry.min(),
        "entry_max_utc": None if entry.empty else entry.max(),
        "exit_min_utc": None if exit_.empty else exit_.min(),
        "exit_max_utc": None if exit_.empty else exit_.max(),
    }


def _probe_symbol(
    symbol: str,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    first_frame: pd.DataFrame | None = None
    first_window: tuple[pd.Timestamp, pd.Timestamp] | None = None

    for left, right in _month_windows(start, end):
        try:
            bars = _fetch_alpaca_1m(
                symbol,
                start_utc=left,
                end_utc=right,
                feed="boats",
            )
            ts = pd.to_datetime(
                bars.get("timestamp"),
                utc=True,
                errors="coerce",
            )
            ts = (
                ts.dropna()
                if ts is not None
                else pd.Series(dtype="datetime64[ns, UTC]")
            )
            row = {
                "window_start_utc": left,
                "window_end_utc": right,
                "rows": int(len(bars)),
                "first_ts_utc": None if ts.empty else ts.min(),
                "last_ts_utc": None if ts.empty else ts.max(),
                "error": None,
            }
        except Exception as exc:
            bars = pd.DataFrame()
            row = {
                "window_start_utc": left,
                "window_end_utc": right,
                "rows": 0,
                "first_ts_utc": None,
                "last_ts_utc": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

        checked.append(row)
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    **row,
                },
                default=str,
                sort_keys=True,
            )
        )

        if row["error"] is None and row["rows"] > 0:
            first_frame = bars
            first_window = (left, right)
            break

    if first_frame is None or first_window is None:
        return {
            "symbol": symbol,
            "status": "NO_DATA_FOUND",
            "first_nonempty_month_start_utc": None,
            "first_bar_utc": None,
            "first_bar_et": None,
            "last_bar_in_first_month_utc": None,
            "first_month_rows": 0,
            "checked_months": checked,
        }

    ts = pd.to_datetime(first_frame["timestamp"], utc=True, errors="coerce").dropna()
    first_bar = ts.min()
    last_bar = ts.max()

    return {
        "symbol": symbol,
        "status": "FOUND",
        "first_nonempty_month_start_utc": first_window[0],
        "first_bar_utc": first_bar,
        "first_bar_et": first_bar.tz_convert(NY),
        "last_bar_in_first_month_utc": last_bar,
        "first_month_rows": int(len(first_frame)),
        "checked_months": checked,
    }


def parse_args() -> argparse.Namespace:
    root = _default_us_etf_root()
    p = argparse.ArgumentParser(
        description="Find the earliest BOATS historical minute data visible to this account."
    )
    p.add_argument("--start", default="2025-01-01")
    p.add_argument(
        "--end",
        default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
    )
    p.add_argument("--symbols", default="SPY,QQQ")
    p.add_argument(
        "--baseline-ledger",
        default=str(
            root
            / "model_lab_v1/results/exit_policy_v1_0_pre2026/"
            "exit_policy_v1_0_1_trade_ledger.parquet"
        ),
    )
    p.add_argument(
        "--output",
        default=str(
            root
            / "model_lab_v1/results/live_policy_replay_v1/"
            "boats_history_boundary.json"
        ),
    )
    return p.parse_args()


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(
            os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
            override=False,
        )
    except ImportError:
        pass

    args = parse_args()
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    end = end + pd.Timedelta(1, unit="D")

    symbols = [
        x.strip().upper()
        for x in str(args.symbols).split(",")
        if x.strip()
    ]
    if not symbols:
        raise RuntimeError("--symbols must contain at least one ticker")

    print("====================================================")
    print("BOATS HISTORICAL BOUNDARY PROBE")
    print("====================================================")
    print("start_utc =", start)
    print("end_utc =", end)
    print("symbols =", symbols)

    results = [
        _probe_symbol(symbol, start=start, end=end)
        for symbol in symbols
    ]
    found = [
        pd.Timestamp(x["first_bar_utc"])
        for x in results
        if x["status"] == "FOUND" and x["first_bar_utc"] is not None
    ]
    first_common_candidate = max(found) if len(found) == len(results) else None

    baseline = _baseline_range(Path(args.baseline_ledger))
    baseline_exit_max = (
        pd.Timestamp(baseline["exit_max_utc"])
        if baseline.get("exit_max_utc") is not None
        else None
    )
    overlap = bool(
        first_common_candidate is not None
        and baseline_exit_max is not None
        and baseline_exit_max >= first_common_candidate
    )

    payload = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "production_changed": False,
        "automation_changed": False,
        "feed": "boats",
        "probe_start_utc": start,
        "probe_end_utc": end,
        "symbols": results,
        "first_common_candidate_utc": first_common_candidate,
        "first_common_candidate_et": (
            None
            if first_common_candidate is None
            else first_common_candidate.tz_convert(NY)
        ),
        "baseline": baseline,
        "baseline_overlaps_boats_history": overlap,
        "next_action": (
            "REPLAY_EXISTING_BASELINE_OVERLAP"
            if overlap
            else "BUILD_POST_BOUNDARY_BASELINE"
        ),
    }

    out = Path(args.output)
    _write_json(out, payload)

    print()
    print("===== SUMMARY =====")
    print("first_common_candidate_utc =", first_common_candidate)
    print(
        "first_common_candidate_et =",
        None
        if first_common_candidate is None
        else first_common_candidate.tz_convert(NY),
    )
    print("baseline_exit_max_utc =", baseline_exit_max)
    print("baseline_overlaps_boats_history =", overlap)
    print("next_action =", payload["next_action"])
    print("output =", out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
