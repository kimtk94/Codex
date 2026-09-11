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

readarray -t SA_PATHS < <("$PY" - <<'PY'
import os
from pathlib import Path
from dotenv import dotenv_values

v = dotenv_values(os.environ["KALMAN_ENV_FILE"])
data_root = Path(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
print(v.get("KALMAN_SA_INPUT_CSV") or data_root / "SeekingAlpha" / "seeking_alpha_daily.csv")
print(v.get("KALMAN_SA_DROP_CSV") or data_root / "SeekingAlpha" / "incoming" / "seeking_alpha_latest.csv")
print(v.get("KALMAN_SA_ARCHIVE_DIR") or data_root / "SeekingAlpha" / "archive")
PY
)

NEEDS_GDRIVE=false
for p in "${SA_PATHS[@]}"; do
  case "$p" in
    "$GDRIVE_MOUNT"|"$GDRIVE_MOUNT"/*) NEEDS_GDRIVE=true ;;
  esac
done

if [ "$NEEDS_GDRIVE" = true ]; then
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
  if ! timeout 20 ls "$GDRIVE_MOUNT" >/dev/null; then
    echo "[FAIL] Google Drive mount is present but unreadable: $GDRIVE_MOUNT" >&2
    exit 21
  fi
fi

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/sa-collector.lock" "$PY" -m engine.sa_collector "$@"
