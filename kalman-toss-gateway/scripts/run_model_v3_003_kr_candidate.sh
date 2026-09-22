#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
MARKET_VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
MARKET_PY="$MARKET_VENV/bin/python"
RESEARCH_PY="$RESEARCH_VENV/bin/python"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

[ -x "$MARKET_PY" ] || { echo "[FAIL] Market Python missing: $MARKET_PY" >&2; exit 10; }
[ -x "$RESEARCH_PY" ] || { echo "[FAIL] Research Python missing: $RESEARCH_PY" >&2; exit 11; }

mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$RESEARCH_PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values
p = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
v = dotenv_values(p) if p.exists() else {}
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

case "$DATA_ROOT" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    mountpoint -q "$GDRIVE_MOUNT" || { echo "[FAIL] Google Drive mount unavailable" >&2; exit 20; }
    timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || { echo "[FAIL] Google Drive unreadable" >&2; exit 21; }
    ;;
esac

MODEL_SPEC="${KALMAN_MODEL_V3003_KR_SPEC:-$APP_ROOT/config/model-v3-kr-candidate-spec.json}"
EVAL_SPEC="${KALMAN_MODEL_V3_EVAL_SPEC:-$APP_ROOT/config/model-v3-evaluation-spec.json}"
UNIVERSE="${KALMAN_MARKET_V2_UNIVERSE:-$APP_ROOT/config/market-data-v2-universe.json}"
MARKET_ROOT="${KALMAN_MARKET_V2_OUTPUT_DIR:-$DATA_ROOT/Market_Data/v2}"
FEATURE_ROOT="${KALMAN_FEATURES_V2002_OUTPUT_DIR:-$DATA_ROOT/Market_Features/v2_002}"
ROOT="${KALMAN_MODEL_V3003_KR_ROOT:-$DATA_ROOT/Market_Model_V3_003_KR}"
MATRIX_DIR="$ROOT/matrices"
MODEL_DIR="$ROOT/frozen"
REPORT="$MODEL_DIR/latest.json"

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/model-v3-003-kr.lock"
flock -n 9 || { echo "MODEL_V3_003_KR_ALREADY_RUNNING" >&2; exit 30; }

echo "=================================================="
echo "KALMAN MODEL V3.003 KR RANK-ALPHA"
echo "=================================================="
echo "Model root     : $ROOT"
echo "Forward start  : 2026-09-23"
echo "Frozen model   : $MODEL_DIR/model.json"
echo "Production     : false"
echo "Neon write     : false"
echo "Trade execution: false"

echo
echo "[1/3] Refresh sparse-safe feature layer"
"$MARKET_PY" -m engine.features_v2_002.cli   --input-dir "$MARKET_ROOT/raw/yfinance"   --output-dir "$FEATURE_ROOT"

echo
echo "[2/3] Build isolated KR V3 matrix"
mkdir -p "$MATRIX_DIR"
"$RESEARCH_PY" -m research.model_v2.build_feature_matrix   --market-root "$MARKET_ROOT"   --feature-root "$FEATURE_ROOT"   --universe "$UNIVERSE"   --spec "$MODEL_SPEC"   --output-dir "$MATRIX_DIR"

echo
echo "[3/3] Freeze-or-track KR candidate"
mkdir -p "$MODEL_DIR"
"$RESEARCH_PY" -m research.model_v3.kr_candidate   --matrix "$MATRIX_DIR/kr_matrix.parquet"   --matrix-manifest "$MATRIX_DIR/kr_matrix_manifest.json"   --model-spec "$MODEL_SPEC"   --evaluation-spec "$EVAL_SPEC"   --output-dir "$MODEL_DIR"

echo
echo "=================================================="
echo "MODEL_V3_003_KR_COMPLETE"
echo "report=$REPORT"
echo "production_write=false"
echo "neon_write=false"
echo "trade_execution=false"
echo "=================================================="
