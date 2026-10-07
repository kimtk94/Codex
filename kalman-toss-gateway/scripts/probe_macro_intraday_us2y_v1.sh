#!/usr/bin/env bash
set -uo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$APP_ROOT/config/macro-event-features-v1.json" ] || {
  echo "[FAIL] macro config missing" >&2
  exit 12
}

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$APP_ROOT"

exec "$PY" -m engine.macro_intraday_us2y_provider_v1 \
  --config "$APP_ROOT/config/macro-event-features-v1.json" \
  --env-file "$ENV_FILE"
