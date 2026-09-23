#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"

export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

exec "$PY" -m research.quant_stack.open_revalidation_backtest "$@"
