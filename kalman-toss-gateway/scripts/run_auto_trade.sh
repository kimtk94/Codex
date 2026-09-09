#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
mkdir -p "$LOCK_DIR" /opt/kalman/logs
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/auto-trade.lock" "$PY" -m engine.auto_trade
