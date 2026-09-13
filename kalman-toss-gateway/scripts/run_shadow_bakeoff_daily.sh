#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

[ -x "$PY" ] || { echo "[FAIL] Research Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] Env missing: $ENV_FILE" >&2; exit 11; }
mkdir -p "$LOCK_DIR" "$LOG_DIR"

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

if [[ "$DATA_ROOT" == "$GDRIVE_MOUNT"* ]]; then
  mountpoint -q "$GDRIVE_MOUNT" || {
    echo "[FAIL] Google Drive mount unavailable" >&2
    exit 20
  }
  timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || {
    echo "[FAIL] Google Drive unreadable" >&2
    exit 21
  }
fi

MODEL_ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
RAW="${KALMAN_SHADOW_BAKEOFF_HIST_RAW:-$DATA_ROOT/Market_Data/v2/raw/historical_2017/multimarket_raw_2017_present.parquet}"
FEATURES="${KALMAN_SHADOW_BAKEOFF_HIST_FEATURES:-$DATA_ROOT/Market_Features/v2/talib/historical_2017/multimarket_features_2017_present_v0_3.parquet}"
OUTPUT_DIR="${KALMAN_SHADOW_BAKEOFF_OUTPUT_DIR:-$MODEL_ROOT/shadow_bakeoff/v1}"
SOURCE_STATUS="$OUTPUT_DIR/latest/source_freshness.json"
BAKEOFF_STATUS="$OUTPUT_DIR/latest/bakeoff_status.json"
SEED_END="${KALMAN_SHADOW_BAKEOFF_SEED_END:-2026-09-11T00:00:00+00:00}"

REFRESH_CURRENT_V2="${KALMAN_SHADOW_BAKEOFF_REFRESH_CURRENT_V2:-}"
SOURCE_REFRESH_SCRIPT="${KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT:-}"

if [ -z "$REFRESH_CURRENT_V2" ]; then
  REFRESH_CURRENT_V2="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(str(v.get("KALMAN_SHADOW_BAKEOFF_REFRESH_CURRENT_V2") or "true").strip().lower())
PY
)"
fi

if [ -z "$SOURCE_REFRESH_SCRIPT" ]; then
  SOURCE_REFRESH_SCRIPT="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(str(v.get("KALMAN_SHADOW_BAKEOFF_SOURCE_REFRESH_SCRIPT") or "").strip())
PY
)"
fi

mkdir -p "$OUTPUT_DIR/latest"

exec 9>"$LOCK_DIR/shadow-bakeoff-daily.lock"
flock -n 9 || {
  echo "SHADOW_BAKEOFF_DAILY_ALREADY_RUNNING" >&2
  exit 40
}

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true; refuse shadow bakeoff daily")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM set; refuse shadow bakeoff daily")
PY

if [ "$REFRESH_CURRENT_V2" = "true" ]; then
  echo "[1/4] Refresh current Market Data / Features V2"
  /bin/bash "$APP_ROOT/scripts/run_v2_shadow_refresh.sh" --skip-finviz
else
  echo "[1/4] Current V2 refresh skipped by configuration"
fi

if [ -n "$SOURCE_REFRESH_SCRIPT" ]; then
  [ -x "$SOURCE_REFRESH_SCRIPT" ] || {
    echo "[FAIL] historical source refresh hook is not executable: $SOURCE_REFRESH_SCRIPT" >&2
    exit 30
  }
  echo "[2/4] Refresh historical integrated sources"
  "$SOURCE_REFRESH_SCRIPT"
else
  echo "[2/4] Historical integrated source refresh hook: NOT CONFIGURED"
fi

echo "[3/4] Historical integrated source freshness gate"
set +e
"$PY" -m research.shadow_bakeoff.source_freshness   --raw "$RAW"   --features "$FEATURES"   --seed-end "$SEED_END"   --output "$SOURCE_STATUS"
SOURCE_RC=$?
set -e

if [ "$SOURCE_RC" -eq 3 ]; then
  echo "SHADOW_BAKEOFF_WAITING_SOURCE_REFRESH"
  cat "$SOURCE_STATUS"
  exit 0
fi
if [ "$SOURCE_RC" -ne 0 ]; then
  echo "[FAIL] Source freshness gate failed with exit=$SOURCE_RC" >&2
  exit "$SOURCE_RC"
fi

echo "[4/4] Run file-only A/B/C forward SHADOW bakeoff"
/bin/bash "$APP_ROOT/scripts/run_shadow_bakeoff_v1.sh"

[ -f "$BAKEOFF_STATUS" ] || {
  echo "[FAIL] bakeoff status missing: $BAKEOFF_STATUS" >&2
  exit 50
}

"$PY" - "$BAKEOFF_STATUS" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
x = json.loads(p.read_text(encoding="utf-8"))
if x.get("status") != "READY":
    raise SystemExit(f"[FAIL] bakeoff status={x.get('status')}")
inv = x.get("invariants") or {}
required_false = [
    "production_write",
    "neon_write",
    "toss_execution",
    "live_execution",
    "auto_trade_visible",
    "dashboard_snapshot_created",
]
for key in required_false:
    if inv.get(key) is not False:
        raise SystemExit(f"[FAIL] invariant {key}={inv.get(key)!r}")
if inv.get("file_only") is not True:
    raise SystemExit("[FAIL] file_only invariant is not true")
print("BAKEOFF_SAFETY_INVARIANTS=PASS")
print("tracking_status=", x.get("tracking_status"))
print("post_seed_return_rows=", x.get("post_seed_return_rows"))
PY

echo "SHADOW_BAKEOFF_DAILY_COMPLETE"
