#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PM_PYTHON:-/home/taehoon/.venvs/kalman-pm-research/bin/python}"
BRIDGE_CONFIG="${KALMAN_VIKE_BRIDGE_CONFIG:-$APP_ROOT/config/prediction-market-vike-bridge-v0.json}"
PREDICTION_CONFIG="${KALMAN_PM_CONFIG:-$APP_ROOT/config/prediction-market-layer-v0.json}"
REFERENCE="${KALMAN_PM_CANONICAL:-/home/taehoon/kalman-data/prediction-market/canonical/prediction_macro_v0.parquet}"
OUTPUT_ROOT="${KALMAN_VIKE_BRIDGE_DIR:-/home/taehoon/kalman-data/prediction-market/vike-bridge-v0}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] research python missing: $PY" >&2
  exit 10
fi

"$PY" -m research.quant_stack.prediction_market_vike_fetch_v0 \
  --bridge-config "$BRIDGE_CONFIG" \
  --prediction-config "$PREDICTION_CONFIG" \
  --output-root "$OUTPUT_ROOT"
FETCH_RC="$?"
if [ "$FETCH_RC" -ne 0 ]; then
  echo "[FAIL] Vike overlap fetch rc=$FETCH_RC" >&2
  exit "$FETCH_RC"
fi

STATUS="$OUTPUT_ROOT/fetch_status.json"
if [ ! -f "$STATUS" ]; then
  echo "[FAIL] missing fetch status: $STATUS" >&2
  exit 20
fi

FETCH_STATUS="$("$PY" - "$STATUS" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["status"])
PY
)"

if [ "$FETCH_STATUS" = "WAITING_FOR_VIKE_KEY" ]; then
  echo "[WAIT] VIKE_API_KEY is not configured; public manifest probe only."
  exit 0
fi

if [ "$FETCH_STATUS" != "READY_FOR_BRIDGE_VALIDATION" ]; then
  echo "[FAIL] unexpected Vike fetch status: $FETCH_STATUS" >&2
  exit 21
fi

"$PY" -m research.quant_stack.prediction_market_vike_bridge_v0 \
  --bridge-config "$BRIDGE_CONFIG" \
  --prediction-config "$PREDICTION_CONFIG" \
  --reference "$REFERENCE" \
  --vike-l1 "$OUTPUT_ROOT/vike_l1_overlap_target.parquet" \
  --markets-json "$OUTPUT_ROOT/vike_target_markets.json" \
  --output-dir "$OUTPUT_ROOT"
exit "$?"
