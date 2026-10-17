#!/usr/bin/env bash

APP_ROOT="${KALMAN_APP_ROOT:-/home/taehoon/.local/share/kalman-jev-shadow}"
ENV_FILE="${KALMAN_ENV_FILE:-/home/taehoon/.config/kalman/jev-shadow.env}"
PY="${KALMAN_PYTHON:-$APP_ROOT/.venv/bin/python}"
CONFIG="${KALMAN_JEV_MACRO_CONFIG:-$APP_ROOT/config/jev-macro-event-v1.3.json}"

export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_JEV_MACRO_CONFIG="$CONFIG"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] Python missing or not executable: $PY" >&2
  exit 10
fi
if [ ! -f "$CONFIG" ]; then
  echo "[FAIL] JEV macro config missing: $CONFIG" >&2
  exit 11
fi

cd "$APP_ROOT" || exit 12
cmd="${1:-status}"
shift || true

case "$cmd" in
  selftest|probe|sync|status)
    "$PY" -m engine.jev_macro_event_v1 --config "$CONFIG" "$cmd" "$@"
    rc=$?
    ;;
  *)
    echo "usage: $0 {selftest|probe|sync|status}" >&2
    rc=2
    ;;
esac
exit "$rc"
