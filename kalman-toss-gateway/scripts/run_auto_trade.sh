#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

# One lock owns the US-only Top-6 planning cycle.
# This scheduled worker never submits broker orders; it emits the current
# rebalance plan from the latest R5.1 US snapshot.
(
  flock -n 9 || exit 0
  PYTHONPATH="$APP_ROOT" "$PY" -m engine.us_top6_rebalancer
) 9>"$LOCK_DIR/auto-trade.lock"
