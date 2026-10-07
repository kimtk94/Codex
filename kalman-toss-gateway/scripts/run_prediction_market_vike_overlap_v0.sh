#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PM_PYTHON:-/home/taehoon/.venvs/kalman-pm-research/bin/python}"
BRIDGE_CONFIG="${KALMAN_VIKE_BRIDGE_CONFIG:-$APP_ROOT/config/prediction-market-vike-bridge-v0.json}"
REFERENCE="${KALMAN_PM_CANONICAL:-/home/taehoon/kalman-data/prediction-market/canonical/prediction_macro_v0.parquet}"
OUTPUT_ROOT="${KALMAN_VIKE_BRIDGE_DIR:-/home/taehoon/kalman-data/prediction-market/vike-bridge-v0}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] research python missing: $PY" >&2
  exit 10
fi

"$PY" -m research.quant_stack.prediction_market_vike_blind_bridge_v0 \
  --bridge-config "$BRIDGE_CONFIG" \
  --reference "$REFERENCE" \
  --output-root "$OUTPUT_ROOT"

exit "$?"
