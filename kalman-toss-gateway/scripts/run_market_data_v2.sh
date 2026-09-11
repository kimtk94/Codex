#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
PY="$VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

[ -x "$PY" ] || {
  echo "[FAIL] Market Tools V2 Python missing: $PY" >&2
  echo "Run scripts/install_market_tools_v2.sh first." >&2
  exit 10
}
[ -d "$APP_ROOT/engine/market_data" ] || {
  echo "[FAIL] Market Data V2 module missing under $APP_ROOT" >&2
  exit 11
}

mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

OUTPUT_OVERRIDE=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    --output-dir)
      if (( i + 1 < ${#args[@]} )); then
        OUTPUT_OVERRIDE="${args[$((i + 1))]}"
      fi
      ;;
    --output-dir=*)
      OUTPUT_OVERRIDE="${args[$i]#--output-dir=}"
      ;;
  esac
done

if [ -n "$OUTPUT_OVERRIDE" ]; then
  OUTPUT_DIR="$OUTPUT_OVERRIDE"
else
  OUTPUT_DIR="$("$PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values

env_file = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
values = dotenv_values(env_file) if Path(env_file).exists() else {}
root = values.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
print(values.get("KALMAN_MARKET_V2_OUTPUT_DIR") or f"{root}/Market_Data/v2")
PY
)"
fi

case "$OUTPUT_DIR" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    if ! mountpoint -q "$GDRIVE_MOUNT"; then
      echo "[FAIL] Google Drive mount unavailable: $GDRIVE_MOUNT" >&2
      exit 20
    fi
    if ! timeout 20 ls "$GDRIVE_MOUNT" >/dev/null; then
      echo "[FAIL] Google Drive mount is present but unreadable: $GDRIVE_MOUNT" >&2
      exit 21
    fi
    ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/market-data-v2.lock" "$PY" -m engine.market_data.cli "$@"
