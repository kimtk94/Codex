#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PM_PYTHON:-/home/taehoon/.venvs/kalman-pm-research/bin/python}"
CONFIG="${KALMAN_PM_US_CONFIG:-$APP_ROOT/config/prediction-market-us-live-v0.json}"
PREDICTION_CONFIG="${KALMAN_PM_CONFIG:-$APP_ROOT/config/prediction-market-layer-v0.json}"
LOCK="/home/taehoon/kalman-data/prediction-market/us-live-v0/collector.lock"

mkdir -p "$(dirname "$LOCK")"

if [ ! -x "$PY" ]; then
  echo "[FAIL] research python missing: $PY" >&2
  exit 10
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[SKIP] Polymarket US collector already running"
  exit 0
fi

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" -m research.quant_stack.prediction_market_us_live_v0 run \
  --config "$CONFIG" \
  --prediction-config "$PREDICTION_CONFIG"

exit "$?"
