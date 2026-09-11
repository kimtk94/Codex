#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$VENV/bin/python"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

SYMBOL="${1:-SPY}"
[ -x "$PY" ] || { echo "[FAIL] Research V2 Python missing: $PY" >&2; exit 10; }

export KALMAN_ENV_FILE="$ENV_FILE"
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

MARKET_ROOT="$DATA_ROOT/Market_Data/v2"
FEATURE_ROOT="$DATA_ROOT/Market_Features/v2"
REPORT_ROOT="$DATA_ROOT/Market_Research/v2"
SAFE_SYMBOL="$(printf '%s' "$SYMBOL" | tr '/-' '__' | tr '[:upper:]' '[:lower:]')"
DATASET="$REPORT_ROOT/datasets/${SAFE_SYMBOL}.parquet"
CONFIG="$APP_ROOT/research/market_tools/configs/rsi_threshold_v1.json"

mkdir -p "$REPORT_ROOT/datasets" "$REPORT_ROOT/reports"

cd "$APP_ROOT"
"$PY" research/market_tools/build_dataset.py \
  --symbol "$SYMBOL" \
  --market-root "$MARKET_ROOT" \
  --feature-root "$FEATURE_ROOT" \
  --output "$DATASET"

"$PY" research/market_tools/run_vectorbt.py \
  --dataset "$DATASET" \
  --config "$CONFIG" \
  --output "$REPORT_ROOT/reports/${SAFE_SYMBOL}_backtest.json"

"$PY" research/market_tools/walk_forward.py \
  --dataset "$DATASET" \
  --output "$REPORT_ROOT/reports/${SAFE_SYMBOL}_walk_forward.json"

printf 'RESEARCH_V2_COMPLETE symbol=%s\n' "$SYMBOL"
