#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-KR_GLOBAL}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
GDRIVE_MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"

mkdir -p "$LOCK_DIR" /opt/kalman/logs
export RUN_MODE="$MODE"
export KALMAN_ENV_FILE="$ENV_FILE"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

DATA_ROOT="$($PY - <<'PY'
import os
from dotenv import dotenv_values
v = dotenv_values(os.environ['KALMAN_ENV_FILE'])
print(v.get('KALMAN_DATA_ROOT') or '/opt/kalman/data')
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
    if ! timeout 20 ls "$DATA_ROOT" >/dev/null; then
      echo "[FAIL] Google Drive mount is present but unreadable: $DATA_ROOT" >&2
      exit 21
    fi
    ;;
esac

case "$MODE" in
  KR_GLOBAL|KR)
    SEED="$DATA_ROOT/Finance_KR/kr_top100_history_monthly_2017_latest.parquet"
    if [ ! -f "$SEED" ]; then
      echo "[FAIL] Required KR seed missing: $SEED" >&2
      exit 22
    fi
    magic="$(timeout 20 head -c 4 "$SEED" || true)"
    if [ "$magic" != "PAR1" ]; then
      echo "[FAIL] KR seed cannot be read through data root: $SEED" >&2
      exit 23
    fi
    ;;
  CRYPTO_GLOBAL|CRYPTO)
    if [ ! -d "$DATA_ROOT/Upbit_BTC" ]; then
      echo "[FAIL] Crypto state directory missing: $DATA_ROOT/Upbit_BTC" >&2
      exit 24
    fi
    ;;
  US)
    ;;
  *)
    echo "[FAIL] Unknown RUN_MODE: $MODE" >&2
    exit 25
    ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/pipeline.lock" "$PY" -m engine.pipeline_entry
