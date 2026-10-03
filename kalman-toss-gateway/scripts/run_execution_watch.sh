#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# Risk exits must remain live even while the hourly US model pipeline owns
# us-cycle.lock. Entries, however, must never evaluate a previous signal while
# that refresh is in flight.
(
  if ! flock -n 8; then
    echo "EXECUTION_WATCH_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=AUTO_TRADE_LOCK_BUSY"
    exit 0
  fi

  echo "EXECUTION_WATCH_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Always reconcile positions first so stop-loss, take-profit,
  # profit-flip, max-hold and Friday-flat remain protected.
  "$PY" -m engine.position_manager
  "$PY" -m engine.trade_mirror

  # Only the entry stage needs the model-cycle lock. If the hourly model
  # refresh is still running, skip entries but keep risk management complete.
  (
    if ! flock -n 9; then
      echo "EXECUTION_ENTRY_SKIP_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ) reason=US_CYCLE_LOCK_BUSY risk_manager=COMPLETED"
      exit 0
    fi

    POLICY="$("$PY" - <<'PY'
import os
from dotenv import dotenv_values
v = dotenv_values(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
print((v.get("AUTO_TRADE_SIGNAL_POLICY") or "").strip().upper())
PY
)"

    if [ "$POLICY" = "R5_LIVE_CONDITIONAL" ]; then
      "$PY" -m engine.r5_conditional_live
    else
      "$PY" -m engine.auto_trade
    fi

    "$PY" -m engine.trade_mirror
  ) 9>"$LOCK_DIR/us-cycle.lock"

  echo "EXECUTION_WATCH_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
) 8>"$LOCK_DIR/auto-trade.lock"
