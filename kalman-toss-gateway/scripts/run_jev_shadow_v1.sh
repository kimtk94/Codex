#!/usr/bin/env bash

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
CONFIG="${KALMAN_JEV_SHADOW_CONFIG:-$APP_ROOT/config/jev-shadow-v1.json}"

export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_JEV_SHADOW_CONFIG="$CONFIG"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] Python missing or not executable: $PY" >&2
  exit 10
fi

if [ ! -f "$CONFIG" ]; then
  echo "[FAIL] JEV config missing: $CONFIG" >&2
  exit 11
fi

cd "$APP_ROOT" || exit 12

cmd="${1:-status}"
shift || true

case "$cmd" in
  selftest|probe|sync|status)
    "$PY" -m engine.jev_shadow_decision_v1 --config "$CONFIG" "$cmd" "$@"
    rc=$?
    ;;
  *)
    echo "usage: $0 {selftest|probe|sync|status}" >&2
    rc=2
    ;;
esac

exit "$rc"
