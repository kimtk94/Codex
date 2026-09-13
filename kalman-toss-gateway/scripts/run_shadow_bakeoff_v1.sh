#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

[ -x "$PY" ] || { echo "[FAIL] Research Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] Env file missing: $ENV_FILE" >&2; exit 11; }
mkdir -p "$LOCK_DIR"

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

env = dotenv_values(Path(sys.argv[1]))
trading = str(env.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(env.get("LIVE_TRADING_CONFIRM") or "").strip()
mode = str(env.get("AUTO_TRADE_EXECUTION_MODE") or "DRY_RUN").strip().upper()

print("TRADING_ENABLED          =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM     =", "SET" if confirm else "(empty)")
print("AUTO_TRADE_EXECUTION_MODE=", mode)

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true; shadow bakeoff refuses to run")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set; shadow bakeoff refuses to run")
PY

DATA_ROOT="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
env = dotenv_values(Path(sys.argv[1]))
print(env.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

if [[ "$DATA_ROOT" == "$GDRIVE_MOUNT"* ]]; then
  mountpoint -q "$GDRIVE_MOUNT" || {
    echo "[FAIL] Google Drive mount unavailable" >&2
    exit 20
  }
  timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || {
    echo "[FAIL] Google Drive unreadable" >&2
    exit 21
  }
fi

MODEL_ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
MATRIX_DIR="${KALMAN_SHADOW_BAKEOFF_MATRIX_DIR:-$MODEL_ROOT/historical_matrices_v1}"
V2_ROOT="${KALMAN_SHADOW_BAKEOFF_V2_ROOT:-$MODEL_ROOT/historical_quant_2017_v2_candidate/20260913_nested_v2_001}"
V3_ROOT="${KALMAN_SHADOW_BAKEOFF_V3_ROOT:-$MODEL_ROOT/historical_quant_2017_v3_candidate/20260913_return_regime_v3_001}"
V34_SUMMARY="${KALMAN_SHADOW_BAKEOFF_V34_SUMMARY:-$MODEL_ROOT/historical_quant_2017_v3_4_allocator_gate/20260913_v3_4_allocator_regime_gate_001/v3_4_summary.json}"
OUTPUT_DIR="${KALMAN_SHADOW_BAKEOFF_OUTPUT_DIR:-$MODEL_ROOT/shadow_bakeoff/v1}"

V2_SPEC="${KALMAN_SHADOW_BAKEOFF_V2_SPEC:-$APP_ROOT/config/model-v2-historical-candidate-spec.json}"
V3_SPEC="${KALMAN_SHADOW_BAKEOFF_V3_SPEC:-$APP_ROOT/config/model-v3-historical-return-regime-spec.json}"

for f in   "$V2_ROOT/historical_v2_candidate_summary.json"   "$V3_ROOT/historical_v3_candidate_summary.json"   "$V34_SUMMARY"   "$V2_SPEC"   "$V3_SPEC"
do
  [ -f "$f" ] || { echo "[FAIL] missing prerequisite: $f" >&2; exit 30; }
done

for f in   "$MATRIX_DIR/us_matrix.parquet"   "$MATRIX_DIR/kr_matrix.parquet"   "$MATRIX_DIR/btc_matrix.parquet"   "$MATRIX_DIR/us_anchor_prices.parquet"   "$MATRIX_DIR/kr_anchor_prices.parquet"   "$MATRIX_DIR/btc_anchor_prices.parquet"
do
  [ -f "$f" ] || { echo "[FAIL] missing matrix/price source: $f" >&2; exit 31; }
done

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/shadow-bakeoff-v1.lock"
flock -n 9 || {
  echo "SHADOW_BAKEOFF_V1_ALREADY_RUNNING" >&2
  exit 40
}

GIT_SHA="${KALMAN_GIT_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"

"$PY" -m research.shadow_bakeoff.runner   --matrix-dir "$MATRIX_DIR"   --v2-root "$V2_ROOT"   --v3-root "$V3_ROOT"   --v2-spec "$V2_SPEC"   --v3-spec "$V3_SPEC"   --v3-4-summary "$V34_SUMMARY"   --output-dir "$OUTPUT_DIR"   --code-sha "$GIT_SHA"

echo
echo "=================================================="
echo "Kalman Forward SHADOW Bake-off V1"
echo "=================================================="
echo "output              : $OUTPUT_DIR"
echo "production write    : FALSE"
echo "Neon write          : FALSE"
echo "Toss execution      : FALSE"
echo "live execution      : FALSE"
echo "dashboard visibility: FALSE"
echo
echo "SHADOW_BAKEOFF_V1_COMPLETE"
