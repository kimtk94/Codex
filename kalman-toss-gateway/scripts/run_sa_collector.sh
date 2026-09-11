#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"

mkdir -p "$LOCK_DIR" "$LOG_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/sa-collector.lock" "$PY" -m engine.sa_collector "$@"
