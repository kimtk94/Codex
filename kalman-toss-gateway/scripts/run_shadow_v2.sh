#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$VENV/bin/python"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

[ -x "$PY" ] || { echo "[FAIL] Research V2 Python missing: $PY" >&2; exit 10; }
mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$PY" - <<'PY'
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

SPEC="${KALMAN_MODEL_V2_SPEC:-$APP_ROOT/config/model-v2-spec.json}"
UNIVERSE="${KALMAN_MARKET_V2_UNIVERSE:-$APP_ROOT/config/market-data-v2-universe.json}"
ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
MATRIX_DIR="$ROOT/matrices"
MODEL_DIR="$ROOT/models"
SHADOW_DIR="$ROOT/shadow"
MARKET_ROOT="${KALMAN_MARKET_V2_OUTPUT_DIR:-$DATA_ROOT/Market_Data/v2}"
FEATURE_ROOT="${KALMAN_FEATURES_V2_OUTPUT_DIR:-$DATA_ROOT/Market_Features/v2}"
MAX_MISSING="${KALMAN_MODEL_V2_MAX_MISSING_FEATURE_RATIO:-0.15}"

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/model-v2-shadow.lock"
flock -n 9 || { echo "MODEL_V2_SHADOW_ALREADY_RUNNING" >&2; exit 30; }

"$PY" -m research.model_v2.build_feature_matrix \
  --market-root "$MARKET_ROOT" \
  --feature-root "$FEATURE_ROOT" \
  --universe "$UNIVERSE" \
  --spec "$SPEC" \
  --output-dir "$MATRIX_DIR"

"$PY" -m research.model_v2.shadow_signal \
  --matrix-dir "$MATRIX_DIR" \
  --model-dir "$MODEL_DIR" \
  --spec "$SPEC" \
  --output-dir "$SHADOW_DIR" \
  --max-missing-feature-ratio "$MAX_MISSING"

printf 'MODEL_V2_SHADOW_COMPLETE root=%s\n' "$ROOT"
