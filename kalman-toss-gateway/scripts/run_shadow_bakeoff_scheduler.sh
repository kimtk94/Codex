#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$VENV/bin/python"
DATA_ROOT_DEFAULT="/opt/kalman/data"
LOG_ROOT="${KALMAN_LOG_ROOT:-/opt/kalman/logs}"
STATE_ROOT="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOG_ROOT" "$STATE_ROOT"

if [ ! -x "$PY" ]; then
  echo "[FAIL] research python missing: $PY" >&2
  exit 10
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[FAIL] env missing: $ENV_FILE" >&2
  exit 11
fi

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$PY" - "$ENV_FILE" "$DATA_ROOT_DEFAULT" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
env = dotenv_values(Path(sys.argv[1]))
print(env.get("KALMAN_DATA_ROOT") or sys.argv[2])
PY
)"
MODEL_ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
OUTPUT_ROOT="${KALMAN_SHADOW_BAKEOFF_OUTPUT_DIR:-$MODEL_ROOT/shadow_bakeoff/v1}"
HEALTH_FILE="$OUTPUT_ROOT/latest/scheduler_status.json"
mkdir -p "$OUTPUT_ROOT/latest"

write_health() {
  local state="$1"
  local rc="$2"
  local message="$3"
  "$PY" - "$HEALTH_FILE" "$state" "$rc" "$message" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "status": sys.argv[2],
    "exit_code": int(sys.argv[3]),
    "message": sys.argv[4],
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "file_only": True,
    "production_write": False,
    "neon_write": False,
    "toss_execution": False,
    "live_execution": False,
}
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(tmp, path)
PY
}

# Cron overlap protection independent from the inner bakeoff lock.
exec 9>"$STATE_ROOT/shadow-bakeoff-scheduler.lock"
if ! flock -n 9; then
  write_health "SKIPPED_ALREADY_RUNNING" 0 "another shadow bakeoff scheduler cycle is active"
  exit 0
fi

# If live trading is ever enabled, do not treat it as a cron failure storm.
LIVE_GATE="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
env = dotenv_values(Path(sys.argv[1]))
trading = str(env.get("TRADING_ENABLED") or "").strip().lower() == "true"
confirm = bool(str(env.get("LIVE_TRADING_CONFIRM") or "").strip())
print("BLOCK" if (trading or confirm) else "OPEN")
PY
)"
if [ "$LIVE_GATE" != "OPEN" ]; then
  write_health "BLOCKED_BY_LIVE_GATE" 0 "TRADING_ENABLED or LIVE_TRADING_CONFIRM prevents research shadow refresh"
  echo "SHADOW_BAKEOFF_SCHEDULER_BLOCKED_BY_LIVE_GATE"
  exit 0
fi

# Refresh the current market/feature snapshots first. These commands are research/shadow only.
# Finviz is intentionally omitted because the forward bakeoff does not consume it.
if [ "${KALMAN_SHADOW_BAKEOFF_REFRESH_CURRENT:-true}" = "true" ]; then
  echo "[1/3] Market Data V2 refresh"
  "$APP_ROOT/scripts/run_market_data_v2.sh"

  echo "[2/3] Features V2 refresh"
  "$APP_ROOT/scripts/run_features_v2.sh"
else
  echo "[1/3] Current Market Data refresh: SKIPPED by config"
  echo "[2/3] Current Features refresh: SKIPPED by config"
fi

echo "[3/3] Forward SHADOW bake-off"
set +e
/bin/bash "$APP_ROOT/scripts/run_shadow_bakeoff_v1.sh"
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  write_health "FAIL" "$RC" "run_shadow_bakeoff_v1.sh failed"
  exit "$RC"
fi

BAKEOFF_STATUS="$OUTPUT_ROOT/latest/bakeoff_status.json"
if [ ! -f "$BAKEOFF_STATUS" ]; then
  write_health "FAIL" 50 "bakeoff_status.json missing after successful runner exit"
  exit 50
fi

TRACKING="$("$PY" - "$BAKEOFF_STATUS" <<'PY'
import json
import sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(p.get("tracking_status") or p.get("status") or "UNKNOWN")
PY
)"

write_health "READY" 0 "tracking_status=$TRACKING"
echo "SHADOW_BAKEOFF_SCHEDULER_COMPLETE tracking_status=$TRACKING"
