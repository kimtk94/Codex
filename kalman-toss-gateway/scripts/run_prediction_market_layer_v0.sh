#!/usr/bin/env bash

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
CONFIG="${KALMAN_PREDICTION_MARKET_CONFIG:-$APP_ROOT/config/prediction-market-layer-v0.json}"

mkdir -p "$LOCK_DIR"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] Python missing: $PY" >&2
  exit 10
fi

if [ ! -f "$CONFIG" ]; then
  echo "[FAIL] prediction market config missing: $CONFIG" >&2
  exit 11
fi

cmd="${1:-collect}"
shift || true

case "$cmd" in
  collect|status|selftest) ;;
  *)
    echo "Usage: $0 {collect|status|selftest} [args...]" >&2
    exit 2
    ;;
esac

cd "$APP_ROOT" || exit 12
exec flock -n "$LOCK_DIR/prediction-market-v0.lock" \
  "$PY" -m engine.prediction_market_layer_v0 "$cmd" --config "$CONFIG" "$@"
