#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/install_server.sh" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=/opt/kalman

if ! command -v rclone >/dev/null 2>&1 || ! command -v fusermount3 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y rclone fuse3
  else
    echo 'rclone/fuse3 are required. Install them before continuing.' >&2
    exit 3
  fi
fi

install -d -m 0750 "$BASE" "$BASE/data" "$BASE/logs" "$BASE/state" "$BASE/secrets"
python3 -m venv "$BASE/.venv"
"$BASE/.venv/bin/pip" install --upgrade pip wheel
"$BASE/.venv/bin/pip" install -r "$SRC/requirements.txt"

rm -rf "$BASE/app"
install -d -m 0755 "$BASE/app"
cp -a "$SRC/app" "$SRC/engine" "$SRC/scripts" "$SRC/config" "$BASE/app/"
chmod +x "$BASE/app/scripts/"*.sh

if [ ! -f "$BASE/.env" ]; then
  cp "$SRC/.env.example" "$BASE/.env"
  chmod 0600 "$BASE/.env"
fi

DATA_ROOT="$($BASE/.venv/bin/python - <<'PY'
from dotenv import dotenv_values
v = dotenv_values('/opt/kalman/.env')
print(v.get('KALMAN_DATA_ROOT') or '/opt/kalman/data')
PY
)"

install -d -m 0755 /content/drive
if [ -e /content/drive/MyDrive ] && [ ! -L /content/drive/MyDrive ]; then
  echo "/content/drive/MyDrive exists and is not a symlink; refusing to overwrite." >&2
  exit 2
fi

case "$DATA_ROOT" in
  /mnt/gdrive|/mnt/gdrive/*)
    if [ -f /etc/rclone/rclone.conf ] && rclone listremotes --config /etc/rclone/rclone.conf | grep -Fxq 'gdrive:'; then
      KALMAN_APP_ROOT="$BASE/app" KALMAN_ENV_FILE="$BASE/.env" \
        bash "$BASE/app/scripts/install_gdrive.sh"
    else
      echo '[WARN] KALMAN_DATA_ROOT uses /mnt/gdrive but rclone gdrive: is not configured yet.'
      echo '       Configure it, then run: sudo /opt/kalman/app/scripts/install_gdrive.sh'
      ln -sfn /mnt/gdrive /content/drive/MyDrive
    fi
    ;;
  *)
    install -d -m 0750 "$DATA_ROOT"
    ln -sfn "$DATA_ROOT" /content/drive/MyDrive
    ;;
esac

cat > /etc/systemd/system/kalman-toss-gateway.service <<'EOF_UNIT'
[Unit]
Description=Kalman Toss Gateway
After=network-online.target kalman-gdrive.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_gateway.sh
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF_UNIT

systemctl daemon-reload
systemctl enable kalman-toss-gateway.service

printf '\nInstalled Kalman runtime. Live trading has NOT been enabled.\n'
printf 'Next:\n'
printf '  1) sudo nano /opt/kalman/.env\n'
printf '  2) sudo /opt/kalman/app/scripts/install_gdrive.sh   # if not already active\n'
printf '  3) sudo /opt/kalman/app/scripts/preflight.sh\n'
printf '  4) sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines\n'
printf '  5) sudo /opt/kalman/app/scripts/install_cron.sh\n'
