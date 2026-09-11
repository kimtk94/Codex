#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PROD_VENV="${KALMAN_PROD_VENV:-/opt/kalman/.venv}"
PROD_PY="$PROD_VENV/bin/python"
DATA_ROOT="/opt/kalman/data"

[ -x "$PROD_PY" ] || { echo "[FAIL] Production Kalman Python missing: $PROD_PY" >&2; exit 10; }
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

DATA_ROOT="$("$PROD_PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values
p = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
v = dotenv_values(p) if p.exists() else {}
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
MODEL_DIR="$ROOT/models"
SHADOW_DIR="$ROOT/shadow"
SHADOW_FILE="$SHADOW_DIR/latest/shadow_signals.json"
STATUS_FILE="$SHADOW_DIR/neon_mirror_status.json"

cd "$APP_ROOT"

# Always refresh the file-based SHADOW first. This remains the canonical research artifact.
"$APP_ROOT/scripts/run_shadow_v2.sh"

"$PROD_PY" -m engine.model_v2_neon_writer \
  --shadow-file "$SHADOW_FILE" \
  --model-dir "$MODEL_DIR" \
  --status-file "$STATUS_FILE"

printf 'MODEL_V2_NEON_SHADOW_MIRROR_COMPLETE status=%s\n' "$STATUS_FILE"
