#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
AUDIT="${LIVE_POLICY_REPLAY_AUDIT:-/mnt/gdrive/US_ETF/model_lab_v1/results/live_policy_replay_v1/live_policy_replay_trade_audit.parquet}"

export KALMAN_ENV_FILE="$ENV_FILE"

echo "===================================================="
echo "LIVE POLICY REPLAY — FEED DIAGNOSTIC"
echo "===================================================="
echo "app_root=$APP_ROOT"
echo "audit=$AUDIT"

if [[ ! -f "$AUDIT" ]]; then
  echo "[FAIL] audit not found: $AUDIT"
  exit 2
fi

cd "$APP_ROOT"
CD_RC=$?
if [[ $CD_RC -ne 0 ]]; then
  echo "[FAIL] cannot cd to app_root=$APP_ROOT rc=$CD_RC"
  exit "$CD_RC"
fi

"$PY" - "$AUDIT" <<'PY'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(
    os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
    override=True,
)

from research.quant_stack.open_revalidation_backtest import (
    NY,
    _fetch_alpaca_1m,
)

audit_path = Path(sys.argv[1])
audit = pd.read_parquet(audit_path).copy()

for col in ("entry_timestamp", "exit_timestamp"):
    if col in audit.columns:
        audit[col] = pd.to_datetime(audit[col], utc=True, errors="coerce")

print()
print("===== PILOT TRADE RANGE =====")
print("rows =", len(audit))

if "entry_timestamp" in audit.columns:
    entries = audit["entry_timestamp"].dropna()
    print("entry_min_utc =", entries.min() if not entries.empty else None)
    print("entry_max_utc =", entries.max() if not entries.empty else None)
    if not entries.empty:
        years = entries.dt.year.value_counts().sort_index().to_dict()
        print("entry_year_counts =", json.dumps(years, sort_keys=True))

if "exit_timestamp" in audit.columns:
    exits = audit["exit_timestamp"].dropna()
    print("exit_min_utc =", exits.min() if not exits.empty else None)
    print("exit_max_utc =", exits.max() if not exits.empty else None)

cols = [
    x for x in (
        "symbol",
        "entry_timestamp",
        "exit_timestamp",
        "cache_path",
        "watch_coverage",
        "position_watch_coverage",
        "execution_watch_coverage",
        "regular_exec_coverage",
        "overnight_watch_coverage",
    )
    if x in audit.columns
]
print()
print("===== FIRST 20 TRADES =====")
print(audit[cols].head(20).to_string(index=False))

print()
print("===== EXISTING CACHE SOURCE COUNTS =====")
cache_paths = []
if "cache_path" in audit.columns:
    cache_paths = list(dict.fromkeys(str(x) for x in audit["cache_path"].dropna()))

summary = {
    "cache_files": 0,
    "missing_cache_files": 0,
    "total_rows": 0,
    "iex_rows": 0,
    "boats_rows": 0,
    "other_rows": 0,
    "caches_with_boats": 0,
}

for raw in cache_paths:
    p = Path(raw)
    if not p.is_file():
        summary["missing_cache_files"] += 1
        print("CACHE_MISSING", p)
        continue

    z = pd.read_parquet(p)
    summary["cache_files"] += 1
    summary["total_rows"] += len(z)

    if "source_feed" in z.columns:
        counts = z["source_feed"].fillna("UNKNOWN").astype(str).value_counts().to_dict()
    else:
        counts = {"UNKNOWN": len(z)}

    summary["iex_rows"] += int(counts.get("iex", 0))
    summary["boats_rows"] += int(counts.get("boats", 0))
    summary["other_rows"] += int(
        sum(v for k, v in counts.items() if k not in {"iex", "boats"})
    )
    if int(counts.get("boats", 0)) > 0:
        summary["caches_with_boats"] += 1

    ts = pd.to_datetime(z.get("timestamp"), utc=True, errors="coerce")
    ts = ts.dropna() if ts is not None else pd.Series(dtype="datetime64[ns, UTC]")

    print(
        json.dumps(
            {
                "cache": str(p),
                "rows": int(len(z)),
                "source_counts": counts,
                "first_ts": None if ts.empty else str(ts.min()),
                "last_ts": None if ts.empty else str(ts.max()),
            },
            default=str,
            sort_keys=True,
        )
    )

print()
print("CACHE_SUMMARY =", json.dumps(summary, sort_keys=True))

print()
print("===== DIRECT BOATS PROBES =====")

def boats_probe(label, symbol, start_et, end_et):
    try:
        bars = _fetch_alpaca_1m(
            symbol,
            start_utc=pd.Timestamp(start_et).tz_convert("UTC"),
            end_utc=pd.Timestamp(end_et).tz_convert("UTC"),
            feed="boats",
        )
        ts = pd.to_datetime(bars.get("timestamp"), utc=True, errors="coerce")
        ts = ts.dropna() if ts is not None else pd.Series(dtype="datetime64[ns, UTC]")
        print(
            json.dumps(
                {
                    "label": label,
                    "symbol": symbol,
                    "start_et": str(start_et),
                    "end_et": str(end_et),
                    "rows": int(len(bars)),
                    "first_ts": None if ts.empty else str(ts.min()),
                    "last_ts": None if ts.empty else str(ts.max()),
                },
                default=str,
                sort_keys=True,
            )
        )
        return len(bars)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "label": label,
                    "symbol": symbol,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                sort_keys=True,
            )
        )
        return None

if not audit.empty and "entry_timestamp" in audit.columns and "symbol" in audit.columns:
    first = audit.dropna(subset=["entry_timestamp", "symbol"]).iloc[0]
    symbol = str(first["symbol"]).upper().replace(".", "-")
    entry_et = pd.Timestamp(first["entry_timestamp"]).tz_convert(NY)
    historical_start = pd.Timestamp(
        datetime.combine(entry_et.date(), dt_time(20, 0), tzinfo=NY)
    )
    historical_end = pd.Timestamp(
        datetime.combine(entry_et.date() + timedelta(days=1), dt_time(4, 0), tzinfo=NY)
    )
    historical_rows = boats_probe(
        "FIRST_PILOT_OVERNIGHT",
        symbol,
        historical_start,
        historical_end,
    )
else:
    historical_rows = None

now_et = pd.Timestamp.now(tz=NY)
recent_end_date = now_et.date()
if now_et.time() < dt_time(4, 20):
    recent_end_date -= timedelta(days=1)
while recent_end_date.weekday() >= 5:
    recent_end_date -= timedelta(days=1)

recent_start = pd.Timestamp(
    datetime.combine(recent_end_date - timedelta(days=1), dt_time(20, 0), tzinfo=NY)
)
recent_end = pd.Timestamp(
    datetime.combine(recent_end_date, dt_time(4, 0), tzinfo=NY)
)
recent_rows = boats_probe(
    "RECENT_COMPLETED_OVERNIGHT",
    "SPY",
    recent_start,
    recent_end,
)

print()
print("===== DIAGNOSIS =====")
if recent_rows is None:
    print("BOATS_RECENT_PROBE=ERROR")
    print("diagnosis=BOATS_ACCESS_OR_REQUEST_ERROR")
elif recent_rows == 0:
    print("BOATS_RECENT_PROBE=EMPTY")
    print("diagnosis=BOATS_ACCESS_OR_DATA_AVAILABILITY_UNRESOLVED")
elif historical_rows == 0:
    print("BOATS_RECENT_PROBE=PASS")
    print("BOATS_HISTORICAL_PROBE=EMPTY")
    print("diagnosis=HISTORICAL_BOATS_DEPTH_GAP")
elif historical_rows is None:
    print("BOATS_RECENT_PROBE=PASS")
    print("BOATS_HISTORICAL_PROBE=ERROR")
    print("diagnosis=HISTORICAL_BOATS_REQUEST_ERROR")
else:
    print("BOATS_RECENT_PROBE=PASS")
    print("BOATS_HISTORICAL_PROBE=PASS")
    print("diagnosis=REPLAY_SESSION_MAPPING_REVIEW_REQUIRED")
PY

RC=$?

echo
echo "===== DIAGNOSTIC RESULT ====="
echo "diagnostic_rc=$RC"
echo "No orders or managed-position writes were performed."

exit "$RC"
