#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

MODE="APPLY"
if [ "${1:-}" = "--dry-run" ]; then
  MODE="DRY_RUN"
  shift
elif [ "${1:-}" = "--apply" ]; then
  MODE="APPLY"
  shift
fi
[ "$#" -eq 0 ] || {
  echo "[FAIL] unknown arguments: $*" >&2
  exit 2
}

[ -x "$PY" ] || { echo "[FAIL] Research Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] Env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$APP_ROOT/config/historical-source-refresh-v1.json" ] || {
  echo "[FAIL] refresh mapping missing" >&2
  exit 12
}
mkdir -p "$LOCK_DIR"

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec 9>"$LOCK_DIR/historical-source-refresh.lock"
flock -n 9 || {
  echo "HISTORICAL_SOURCE_REFRESH_ALREADY_RUNNING" >&2
  exit 40
}

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

v = dotenv_values(Path(sys.argv[1]))
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
mode = str(v.get("AUTO_TRADE_EXECUTION_MODE") or "DRY_RUN").strip().upper()

print("TRADING_ENABLED          =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM     =", "SET" if confirm else "(empty)")
print("AUTO_TRADE_EXECUTION_MODE=", mode)

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true; refuse historical source refresh")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM set; refuse historical source refresh")
PY

DATA_ROOT="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v = dotenv_values(Path(sys.argv[1]))
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

MARKET_ROOT="${KALMAN_MARKET_V2_OUTPUT_DIR:-$DATA_ROOT/Market_Data/v2}"
RAW="${KALMAN_SHADOW_BAKEOFF_HIST_RAW:-$DATA_ROOT/Market_Data/v2/raw/historical_2017/multimarket_raw_2017_present.parquet}"
FEATURES="${KALMAN_SHADOW_BAKEOFF_HIST_FEATURES:-$DATA_ROOT/Market_Features/v2/talib/historical_2017/multimarket_features_2017_present_v0_3.parquet}"
MODEL_ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
OUTPUT_DIR="${KALMAN_SHADOW_BAKEOFF_OUTPUT_DIR:-$MODEL_ROOT/shadow_bakeoff/v1}"
STATUS="$OUTPUT_DIR/latest/historical_source_refresh.json"
MAPPING="${KALMAN_HISTORICAL_REFRESH_MAPPING:-$APP_ROOT/config/historical-source-refresh-v1.json}"
BACKUP_ROOT="${KALMAN_HISTORICAL_REFRESH_BACKUP_ROOT:-$DATA_ROOT/Market_Data/v2/raw/historical_2017/_refresh_backups}"
PARITY_MIN="${KALMAN_HISTORICAL_REFRESH_PARITY_MIN_POINTS:-30}"
PARITY_MAX="${KALMAN_HISTORICAL_REFRESH_MAX_PARITY_ERROR:-0.03}"
OVERLAP_MIN="${KALMAN_HISTORICAL_REFRESH_SOURCE_OVERLAP_MIN_POINTS:-5}"
OVERLAP_MAX="${KALMAN_HISTORICAL_REFRESH_MAX_SOURCE_CLOSE_REL_ERROR:-0.01}"

for f in "$RAW" "$FEATURES" "$MAPPING"; do
  [ -f "$f" ] || { echo "[FAIL] missing required file: $f" >&2; exit 20; }
done
[ -d "$MARKET_ROOT" ] || { echo "[FAIL] market root missing: $MARKET_ROOT" >&2; exit 21; }
mkdir -p "$OUTPUT_DIR/latest"

ARGS=(
  -m research.shadow_bakeoff.historical_source_refresh
  --raw "$RAW"
  --features "$FEATURES"
  --market-root "$MARKET_ROOT"
  --mapping "$MAPPING"
  --output-status "$STATUS"
  --backup-root "$BACKUP_ROOT"
  --parity-min-points "$PARITY_MIN"
  --max-parity-error "$PARITY_MAX"
  --source-overlap-min-points "$OVERLAP_MIN"
  --max-source-close-relative-error "$OVERLAP_MAX"
)

if [ "$MODE" = "APPLY" ]; then
  ARGS+=(--apply)
fi

echo "============================================================"
echo "Kalman Historical Integrated Source Refresh V1"
echo "============================================================"
echo "Mode        : $MODE"
echo "Market root : $MARKET_ROOT"
echo "Raw         : $RAW"
echo "Features    : $FEATURES"
echo "Mapping     : $MAPPING"
echo "Status      : $STATUS"
echo "Research    : ONLY"
echo "Live/Toss   : FALSE"
echo "Neon/Prod   : FALSE"
echo

cd "$APP_ROOT"
"$PY" "${ARGS[@]}"

echo
echo "============================================================"
echo "HISTORICAL_SOURCE_REFRESH_COMPLETE"
echo "mode=$MODE"
echo "status=$STATUS"
echo "============================================================"
