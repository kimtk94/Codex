#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/install_gdrive.sh" >&2
  exit 1
fi

BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
RCLONE_CONFIG="${KALMAN_RCLONE_CONFIG:-/etc/rclone/rclone.conf}"
REMOTE="${KALMAN_GDRIVE_REMOTE:-gdrive}"
MOUNT="${KALMAN_GDRIVE_MOUNT:-/mnt/gdrive}"
SERVICE=kalman-gdrive.service

for cmd in rclone fusermount3 mountpoint systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 2
  }
done

[ -f "$RCLONE_CONFIG" ] || {
  echo "Missing rclone config: $RCLONE_CONFIG" >&2
  echo "Create it first with: sudo rclone config --config $RCLONE_CONFIG" >&2
  exit 3
}

if ! rclone listremotes --config "$RCLONE_CONFIG" | grep -Fxq "${REMOTE}:"; then
  echo "rclone remote '${REMOTE}:' not found in $RCLONE_CONFIG" >&2
  exit 4
fi

rclone lsd "${REMOTE}:" --config "$RCLONE_CONFIG" >/dev/null

install -d -m 0755 "$MOUNT" /var/cache/rclone /content/drive
install -m 0644 "$APP_ROOT/config/kalman-gdrive.service" "/etc/systemd/system/$SERVICE"
touch /var/log/kalman-rclone.log
chmod 0644 /var/log/kalman-rclone.log

if mountpoint -q "$MOUNT" && ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
  echo "Unmounting existing unmanaged mount at $MOUNT"
  fusermount3 -uz "$MOUNT" || true
  sleep 2
fi

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

mounted=false
for _ in $(seq 1 20); do
  if mountpoint -q "$MOUNT"; then
    mounted=true
    break
  fi
  sleep 1
done

if [ "$mounted" != true ]; then
  echo "Google Drive mount did not become ready: $MOUNT" >&2
  journalctl -u "$SERVICE" -n 50 --no-pager >&2 || true
  exit 5
fi

timeout 20 ls "$MOUNT" >/dev/null

if [ -f "$MOUNT/Finance_KR/kr_top100_history_monthly_2017_latest.parquet" ]; then
  magic="$(timeout 20 head -c 4 "$MOUNT/Finance_KR/kr_top100_history_monthly_2017_latest.parquet")"
  if [ "$magic" != "PAR1" ]; then
    echo "KR seed exists but is not readable as a Parquet file (magic=$magic)" >&2
    exit 6
  fi
  echo "[OK] KR seed readable through rclone mount"
else
  echo "[WARN] Finance_KR seed not found yet under $MOUNT"
fi

if [ -e /content/drive/MyDrive ] && [ ! -L /content/drive/MyDrive ]; then
  echo "/content/drive/MyDrive exists and is not a symlink; refusing to overwrite." >&2
  exit 7
fi
ln -sfn "$MOUNT" /content/drive/MyDrive

if [ -f "$ENV_FILE" ]; then
  if grep -q '^KALMAN_DATA_ROOT=' "$ENV_FILE"; then
    sed -i "s|^KALMAN_DATA_ROOT=.*|KALMAN_DATA_ROOT=$MOUNT|" "$ENV_FILE"
  else
    printf '\nKALMAN_DATA_ROOT=%s\n' "$MOUNT" >> "$ENV_FILE"
  fi
fi

echo "[PASS] ${REMOTE}: mounted at $MOUNT and enabled at boot"
echo "       /content/drive/MyDrive -> $MOUNT"
