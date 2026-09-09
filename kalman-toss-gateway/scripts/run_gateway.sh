#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
set -a
[ -f "$ENV_FILE" ] && source "$ENV_FILE"
set +a
cd "$APP_ROOT"
exec /opt/kalman/.venv/bin/uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8787}"
