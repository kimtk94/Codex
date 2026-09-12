#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="${VENV}/bin/python"
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
ROOT="${KALMAN_MODEL_V2_ROOT:-$DATA_ROOT/Market_Model_V2}"
MATRIX_DIR="${KALMAN_MODEL_V2_MATRIX_DIR:-$ROOT/matrices}"
OUTPUT_DIR="${KALMAN_HISTORICAL_QUANT_ROOT:-$ROOT/historical_quant_v1}"

TRAIN="${KALMAN_WF_TRAIN:-504}"
VALID="${KALMAN_WF_VALID:-63}"
TEST="${KALMAN_WF_TEST:-126}"
MAX_HOLD="${KALMAN_WF_MAX_HOLD_BARS:-20}"
START_DATE="${KALMAN_WF_START_DATE:-2017-01-01}"

cd "$APP_ROOT"
exec 9>"$LOCK_DIR/historical-quant-v1.lock"
flock -n 9 || { echo "HISTORICAL_QUANT_V1_ALREADY_RUNNING" >&2; exit 30; }

GIT_SHA="${KALMAN_GIT_SHA:-}"
if [ -z "$GIT_SHA" ] && command -v git >/dev/null 2>&1; then
  GIT_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
fi

ARGS=(
  -m research.quant_stack.experiment_runner
  --matrix-dir "$MATRIX_DIR"
  --spec "$SPEC"
  --output-dir "$OUTPUT_DIR"
  --start-date "$START_DATE"
  --train "$TRAIN"
  --valid "$VALID"
  --test "$TEST"
  --max-hold-bars "$MAX_HOLD"
)

if [ -n "$GIT_SHA" ]; then
  ARGS+=(--git-sha "$GIT_SHA")
fi

"$PY" "${ARGS[@]}"

printf 'HISTORICAL_QUANT_V1_COMPLETE root=%s start=%s\n' "$OUTPUT_DIR" "$START_DATE"
