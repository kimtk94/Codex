#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

mkdir -p "$LOCK_DIR" "$LOG_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

DATA_ROOT="$($PY - <<'PY'
import os
from dotenv import dotenv_values
v = dotenv_values(os.environ["KALMAN_ENV_FILE"])
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)"

case "$DATA_ROOT" in
  "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*)
    if ! mountpoint -q "$GDRIVE_MOUNT"; then
      echo "[WARN] Google Drive is not mounted; asking systemd to recover it"
      systemctl start kalman-gdrive.service || true
      for _ in $(seq 1 15); do
        mountpoint -q "$GDRIVE_MOUNT" && break
        sleep 1
      done
    fi
    if ! mountpoint -q "$GDRIVE_MOUNT"; then
      echo "[FAIL] Google Drive mount unavailable: $GDRIVE_MOUNT" >&2
      exit 20
    fi
    ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/sa-us-btc-features.lock" "$PY" -m engine.sa_us_btc_features "$@"
