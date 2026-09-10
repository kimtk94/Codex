#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# One lock owns the full cycle. Exits/reconciliation always run before a new
# entry so a due position cannot race with a fresh BUY.
(
  flock -n 9 || exit 0
  "$PY" -m engine.position_manager
  "$PY" -m engine.auto_trade
) 9>"$LOCK_DIR/auto-trade.lock"
