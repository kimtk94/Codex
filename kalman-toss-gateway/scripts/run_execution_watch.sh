#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# The hourly US model cycle owns us-cycle.lock while it refreshes and commits
# strategy_signal. A watcher must never evaluate the previous signal while that
# refresh is in flight. The same lock also prevents overlapping watcher ticks.
(
  if ! flock -n 9; then
    echo "EXECUTION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=US_CYCLE_LOCK_BUSY"
    exit 0
  fi

  # Keep the lock ordering identical to run_us_cycle.sh -> run_auto_trade.sh:
  # us-cycle.lock first, auto-trade.lock second. This also serializes the
  # watcher against any manual invocation of run_auto_trade.sh.
  (
    if ! flock -n 8; then
      echo "EXECUTION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=AUTO_TRADE_LOCK_BUSY"
      exit 0
    fi

    echo "EXECUTION_WATCH_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Lightweight execution-only cycle. Do NOT run the market/model pipeline
    # here: the 60-minute R5.1 signal cadence remains unchanged.
    #
    # 1) reconcile entries/add-ons/exits and apply intrabar risk exits;
    # 2) catch up any fresh, eligible signal not yet executed;
    # 3) persist the resulting execution/position audit.
    "$PY" -m engine.position_manager
    "$PY" -m engine.auto_trade
    "$PY" -m engine.trade_mirror

    echo "EXECUTION_WATCH_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ) 8>"$LOCK_DIR/auto-trade.lock"
) 9>"$LOCK_DIR/us-cycle.lock"
