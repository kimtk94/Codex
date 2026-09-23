#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# Daytime position-only watch. It never rebuilds the R5.1 model and never
# creates BUY orders. It records managed-position P/L trajectories so a
# profit-to-loss deterioration can be carried into the next executable
# fractional-order window and revalidated there.
(
  if ! flock -n 9; then
    echo "POSITION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=US_CYCLE_LOCK_BUSY"
    exit 0
  fi

  (
    if ! flock -n 8; then
      echo "POSITION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=AUTO_TRADE_LOCK_BUSY"
      exit 0
    fi

    echo "POSITION_WATCH_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    "$PY" -m engine.position_manager
    "$PY" -m engine.trade_mirror
    echo "POSITION_WATCH_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ) 8>"$LOCK_DIR/auto-trade.lock"
) 9>"$LOCK_DIR/us-cycle.lock"
