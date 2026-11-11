#!/usr/bin/env bash

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
RUN="$APP_ROOT/scripts/run_jev_shadow_v1.sh"
CONFIG="$APP_ROOT/config/jev-shadow-v1.json"
KEY_FILE="${JEV_GATEWAY_KEY_FILE:-/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out}"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

if [ "$(id -u)" -ne 0 ]; then
  fail "Run as root: /opt/kalman/app/scripts/install_jev_shadow_v1.sh"
fi

[ -x "$PY" ] || fail "Python missing or not executable: $PY"
[ -f "$ENV_FILE" ] || fail "Env file missing: $ENV_FILE"
[ -f "$RUN" ] || fail "Runner missing: $RUN"
[ -f "$CONFIG" ] || fail "Config missing: $CONFIG"
[ -f "$KEY_FILE" ] || fail "JEV Gateway key file missing: $KEY_FILE"

chmod +x "$RUN" || fail "Could not make runner executable"

echo "[1/5] Verify research-only source invariants"
grep -q '"shadow_only": true' "$CONFIG" || fail "shadow_only invariant missing"
grep -q '"can_veto_live": false' "$CONFIG" || fail "can_veto_live invariant missing"
grep -q '"can_size_live": false' "$CONFIG" || fail "can_size_live invariant missing"

echo "[2/5] Selftest"
KALMAN_ENV_FILE="$ENV_FILE" "$RUN" selftest || fail "JEV selftest failed"

echo "[3/5] Verify Neon schema"
KALMAN_ENV_FILE="$ENV_FILE" "$PY" - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
if not db_url:
    raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing")

required = (
    "public.jev_shadow_decision_v1",
    "public.v_jev_shadow_decision_latest_v1",
    "public.v_jev_shadow_decision_summary_v1",
)
with psycopg.connect(db_url, connect_timeout=15) as conn:
    row = conn.execute(
        "SELECT " + ",".join("to_regclass(%s)" for _ in required),
        required,
    ).fetchone()
missing = [name for name, value in zip(required, row) if value is None]
if missing:
    raise SystemExit("JEV shadow schema missing: " + ", ".join(missing))
print("[PASS] JEV shadow schema present")
PY
rc=$?
[ "$rc" -eq 0 ] || fail "Neon schema verification failed"

echo "[4/5] Install systemd service/timer"
cat > /etc/systemd/system/kalman-jev-shadow.service <<'EOF'
[Unit]
Description=Kalman JEV Shadow Decision V1
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
Environment=JEV_SHADOW_ENABLED=true
Environment=JEV_SHADOW_ONLY=true
Environment=JEV_CAN_VETO_LIVE=false
Environment=JEV_CAN_SIZE_LIVE=false
ExecStart=/opt/kalman/app/scripts/run_jev_shadow_v1.sh sync
Nice=10
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-jev-shadow.timer <<'EOF'
[Unit]
Description=Refresh Kalman JEV shadow decisions every 15 minutes

[Timer]
OnBootSec=7min
OnUnitActiveSec=15min
AccuracySec=60s
Persistent=true
Unit=kalman-jev-shadow.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload || fail "systemctl daemon-reload failed"
systemctl enable --now kalman-jev-shadow.timer || fail "Could not enable JEV timer"

echo "[5/5] Verify installed timer"
systemctl is-enabled kalman-jev-shadow.timer || fail "JEV timer is not enabled"
systemctl list-timers --all 'kalman-jev-shadow*' --no-pager || true

echo "JEV Shadow V1 installed: observation-only, no live veto, no live sizing."
