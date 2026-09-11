#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
PY="$VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

[ -x "$PY" ] || { echo "[FAIL] V2 Python missing: $PY" >&2; exit 10; }
mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

FEATURE_DIR="$("$PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values
p = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
v = dotenv_values(p) if Path(p).exists() else {}
root = v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
print(v.get("KALMAN_FEATURES_V2_OUTPUT_DIR") or f"{root}/Market_Features/v2")
PY
)"

case "$FEATURE_DIR" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    mountpoint -q "$GDRIVE_MOUNT" || { echo "[FAIL] Google Drive mount unavailable" >&2; exit 20; }
    timeout 20 ls "$GDRIVE_MOUNT" >/dev/null || { echo "[FAIL] Google Drive unreadable" >&2; exit 21; }
    ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/features-v2.lock" "$PY" -m engine.features_v2.cli "$@"
