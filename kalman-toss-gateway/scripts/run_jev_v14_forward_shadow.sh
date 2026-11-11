#!/usr/bin/env bash

APP_ROOT="${KALMAN_APP_ROOT:-/home/taehoon/.local/share/kalman-jev-shadow}"
ENV_FILE="${KALMAN_ENV_FILE:-/home/taehoon/.config/kalman/jev-shadow.env}"
PY="${KALMAN_PYTHON:-$APP_ROOT/.venv/bin/python}"
CONFIG="${KALMAN_JEV_V14_CONFIG:-$APP_ROOT/config/jev-macro-forward-v1.4.json}"

export KALMAN_ENV_FILE="$ENV_FILE"
export KALMAN_JEV_V14_CONFIG="$CONFIG"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export JEV_GATEWAY_KEY_FILE="${JEV_GATEWAY_KEY_FILE:-/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] Python missing or not executable: $PY" >&2
  exit 10
fi
if [ ! -f "$CONFIG" ]; then
  echo "[FAIL] V1.4 config missing: $CONFIG" >&2
  exit 11
fi
if [ ! -f "$APP_ROOT/research/jev_v14_forward_shadow.py" ]; then
  echo "[FAIL] V1.4 module missing" >&2
  exit 12
fi

cd "$APP_ROOT" || exit 13
cmd="${1:-status}"
shift || true

case "$cmd" in
  collect|sync|status|selftest)
    "$PY" research/jev_v14_forward_shadow.py --config "$CONFIG" "$cmd" "$@"
    rc=$?
    ;;
  *)
    echo "usage: $0 {collect|sync|status|selftest}" >&2
    rc=2
    ;;
esac
exit "$rc"
