#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/install_server.sh" >&2
  exit 1
fi
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=/opt/kalman
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
install -d -m 0755 /content/drive
if [ -e /content/drive/MyDrive ] && [ ! -L /content/drive/MyDrive ]; then
  echo "/content/drive/MyDrive exists and is not a symlink; refusing to overwrite." >&2
  exit 2
fi
ln -sfn "$BASE/data" /content/drive/MyDrive
cat > /etc/systemd/system/kalman-toss-gateway.service <<'EOF'
[Unit]
Description=Kalman Toss Gateway
After=network-online.target
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
EOF
systemctl daemon-reload
systemctl enable kalman-toss-gateway.service
printf '\nInstalled Kalman runtime. Live trading has NOT been enabled.\n'
printf 'Next:\n'
printf '  1) sudo nano /opt/kalman/.env\n'
printf '  2) copy legacy data to /opt/kalman/data/{Finance_KR,Upbit_BTC}\n'
printf '  3) sudo /opt/kalman/app/scripts/preflight.sh\n'
printf '  4) sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines\n'
printf '  5) sudo /opt/kalman/app/scripts/install_cron.sh\n'
