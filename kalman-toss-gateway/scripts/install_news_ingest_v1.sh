#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo /opt/kalman/app/scripts/install_news_ingest_v1.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RUN="$APP_ROOT/scripts/run_news_ingest_v1.sh"

[ -x "$RUN" ] || chmod +x "$RUN"
install -d -m 0750 /var/lib/kalman/news /opt/kalman/state/news /opt/kalman/logs

KALMAN_ENV_FILE="$ENV_FILE" "$RUN" selftest

cat > /etc/systemd/system/kalman-news-collect.service <<'EOF'
[Unit]
Description=Kalman News/Event V1 collector
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_news_ingest_v1.sh collect
Nice=5
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-news-collect.timer <<'EOF'
[Unit]
Description=Collect Kalman news/events every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=20s
Persistent=true
Unit=kalman-news-collect.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/kalman-news-sync.service <<'EOF'
[Unit]
Description=Kalman News/Event V1 Neon and Drive sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_news_ingest_v1.sh sync
Nice=5
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-news-sync.timer <<'EOF'
[Unit]
Description=Sync Kalman news/events every 10 minutes

[Timer]
OnBootSec=4min
OnUnitActiveSec=10min
AccuracySec=30s
Persistent=true
Unit=kalman-news-sync.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/kalman-news-coverage.service <<'EOF'
[Unit]
Description=Kalman News/Event V1 coverage audit
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_news_ingest_v1.sh coverage
Nice=5
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-news-coverage.timer <<'EOF'
[Unit]
Description=Audit Kalman news/event coverage hourly

[Timer]
OnBootSec=7min
OnUnitActiveSec=1h
AccuracySec=1min
Persistent=true
Unit=kalman-news-coverage.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now kalman-news-collect.timer
systemctl enable --now kalman-news-sync.timer
systemctl enable --now kalman-news-coverage.timer

echo "Installed Kalman news/event timers."
systemctl list-timers --all 'kalman-news-*' --no-pager || true
