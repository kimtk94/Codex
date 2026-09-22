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

[ -x "$MARKET_PY" ] || { echo "[FAIL] Market V2 Python missing: $MARKET_PY" >&2; exit 10; }
[ -x "$RESEARCH_PY" ] || { echo "[FAIL] Research V2 Python missing: $RESEARCH_PY" >&2; exit 11; }

mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$RESEARCH_PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values
p=Path(os.environ.get("KALMAN_ENV_FILE","/opt/kalman/.env"))
v=dotenv_values(p) if p.exists() else {}
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

case "$DATA_ROOT" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    mountpoint -q "$GDRIVE_MOUNT" || { echo "[FAIL] Google Drive mount unavailable" >&2; exit 20; }
    timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || { echo "[FAIL] Google Drive unreadable" >&2; exit 21; }
    ;;
esac

SPEC="${KALMAN_MODEL_V2002_SPEC:-$APP_ROOT/config/model-v2-002-candidate-spec.json}"
UNIVERSE="${KALMAN_MARKET_V2_UNIVERSE:-$APP_ROOT/config/market-data-v2-universe.json}"
MARKET_ROOT="${KALMAN_MARKET_V2_OUTPUT_DIR:-$DATA_ROOT/Market_Data/v2}"
FEATURE_ROOT="${KALMAN_FEATURES_V2002_OUTPUT_DIR:-$DATA_ROOT/Market_Features/v2_002}"
ROOT="${KALMAN_MODEL_V2002_ROOT:-$DATA_ROOT/Market_Model_V2_002_Candidate}"
MATRIX_DIR="$ROOT/matrices"
MODEL_DIR="$ROOT/models"
BASELINE_MODEL_DIR="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}/models"
REPORT="$ROOT/evaluation/latest.json"

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/model-v2-002-candidate.lock"
flock -n 9 || { echo "MODEL_V2_002_CANDIDATE_ALREADY_RUNNING" >&2; exit 30; }

echo "=================================================="
echo "KALMAN MODEL V2.002 CANDIDATE"
echo "=================================================="
echo "Feature root : $FEATURE_ROOT"
echo "Model root   : $ROOT"
echo "Baseline     : $BASELINE_MODEL_DIR"
echo "Neon write   : false"
echo "Trade exec   : false"

echo
echo "[1/4] Build isolated sparse-safe TA-Lib features"
"$MARKET_PY" -m engine.features_v2_002.cli   --input-dir "$MARKET_ROOT/raw/yfinance"   --output-dir "$FEATURE_ROOT"

echo
echo "[2/4] Build isolated V2.002 feature matrices"
"$RESEARCH_PY" -m research.model_v2.build_feature_matrix   --market-root "$MARKET_ROOT"   --feature-root "$FEATURE_ROOT"   --universe "$UNIVERSE"   --spec "$SPEC"   --output-dir "$MATRIX_DIR"

echo
echo "[3/4] Train chronologically calibrated candidates"
"$RESEARCH_PY" -m research.model_v2_002.train_candidates   --matrix-dir "$MATRIX_DIR"   --spec "$SPEC"   --output-dir "$MODEL_DIR"

echo
echo "[4/4] Compare with frozen V2.001"
"$RESEARCH_PY" -m research.model_v2_002.evaluate_candidate   --matrix-dir "$MATRIX_DIR"   --model-dir "$MODEL_DIR"   --baseline-model-dir "$BASELINE_MODEL_DIR"   --output-file "$REPORT"

echo
echo "=================================================="
echo "MODEL_V2_002_CANDIDATE_COMPLETE"
echo "report=$REPORT"
echo "production_write=false"
echo "neon_write=false"
echo "trade_execution=false"
echo "=================================================="
