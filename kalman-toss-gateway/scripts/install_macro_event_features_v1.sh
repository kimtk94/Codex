#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo /opt/kalman/app/scripts/install_macro_event_features_v1.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
RUN="$APP_ROOT/scripts/run_macro_event_features_v1.sh"
SCHEMA="$APP_ROOT/research/quant_stack/macro_event_features_v1.sql"

[ -x "$RUN" ] || chmod +x "$RUN"
[ -f "$SCHEMA" ] || { echo "[FAIL] schema missing: $SCHEMA" >&2; exit 12; }

echo "[1/4] Apply additive macro feature schema"
KALMAN_ENV_FILE="$ENV_FILE" "$PY" - "$SCHEMA" <<'PY'
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

env_file = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
load_dotenv(env_file, override=True)
db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
if not db_url:
    raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing")

sql = Path(sys.argv[1]).read_text(encoding="utf-8")
statements = [x.strip() for x in sql.split(";") if x.strip()]
with psycopg.connect(db_url, connect_timeout=15) as conn:
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()
print(f"[PASS] applied {len(statements)} schema statements")
PY

echo "[2/4] Selftest"
KALMAN_ENV_FILE="$ENV_FILE" "$RUN" selftest

echo "[3/4] Install systemd service/timer"
cat > /etc/systemd/system/kalman-macro-feature.service <<'EOF'
[Unit]
Description=Kalman Macro Event Challenger Feature V1
After=network-online.target kalman-news-sync.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_macro_event_features_v1.sh build
Nice=5
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-macro-feature.timer <<'EOF'
[Unit]
Description=Build Kalman macro event challenger features every 15 minutes

[Timer]
OnBootSec=9min
OnUnitActiveSec=15min
AccuracySec=30s
Persistent=true
Unit=kalman-macro-feature.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now kalman-macro-feature.timer

echo "[4/4] Installed"
systemctl list-timers --all 'kalman-macro-feature*' --no-pager || true
echo "Macro feature timer installed. Feature execution remains fail-closed unless KALMAN_MACRO_FEATURES_ENABLED=true."
