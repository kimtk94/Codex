#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"

mkdir -p "$LOCK_DIR" "$LOG_DIR"
export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"

case "$PROFILE" in
  BTC)
    RUNNER="$APP_ROOT/scripts/run_model_v3_003_btc_tail.sh"
    ;;
  US)
    RUNNER="$APP_ROOT/scripts/run_model_v3_003_us_hurdle.sh"
    ;;
  KR)
    RUNNER="$APP_ROOT/scripts/run_model_v3_004_kr_joint_gate.sh"
    ;;
  *)
    echo "[FAIL] usage: $0 {BTC|US|KR}" >&2
    exit 2
    ;;
esac

TRACKER="$APP_ROOT/scripts/run_v3_shadow_tracker.sh"

[ -x "$RUNNER" ] || { echo "[FAIL] runner missing: $RUNNER" >&2; exit 10; }
[ -x "$TRACKER" ] || { echo "[FAIL] tracker missing: $TRACKER" >&2; exit 11; }

exec 9>"$LOCK_DIR/v3-shadow-cycle-$PROFILE.lock"
flock -n 9 || {
  echo "V3_SHADOW_CYCLE_${PROFILE}_ALREADY_RUNNING"
  exit 0
}

STAMP="$(date +%Y%m%d_%H%M%S)"
echo "=================================================="
echo "KALMAN V3 SHADOW CYCLE"
echo "profile=$PROFILE"
echo "started_at=$(date --iso-8601=seconds)"
echo "production_write=false"
echo "neon_write=false"
echo "trade_execution=false"
echo "=================================================="

"$RUNNER"

echo
echo "===== REFRESH UNIFIED TRACKER ====="
"$TRACKER"

echo
echo "=================================================="
echo "V3_SHADOW_CYCLE_COMPLETE"
echo "profile=$PROFILE"
echo "completed_at=$(date --iso-8601=seconds)"
echo "stamp=$STAMP"
echo "=================================================="
