#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo /opt/kalman/app/scripts/install_macro_shadow_eval_v1.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
RUN="$APP_ROOT/scripts/run_macro_shadow_eval_v1.sh"

[ -x "$RUN" ] || chmod +x "$RUN"

echo "[1/4] Verify shadow evaluation schema"
KALMAN_ENV_FILE="$ENV_FILE" "$PY" - <<'PY'
import os
import psycopg
from dotenv import load_dotenv

load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
if not db_url:
    raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing")

required = (
    "public.macro_shadow_evaluation_v1",
    "public.v_macro_shadow_eval_summary_v1",
    "public.v_macro_shadow_eval_readiness_v1",
    "public.v_macro_shadow_eval_free_reaction_v1",
)
with psycopg.connect(db_url, connect_timeout=15) as conn:
    row = conn.execute(
        "SELECT " + ",".join("to_regclass(%s)" for _ in required),
        required,
    ).fetchone()
missing = [name for name, value in zip(required, row) if value is None]
if missing:
    raise SystemExit(
        "Macro shadow evaluation schema is missing: " + ", ".join(missing)
        + ". Apply research/quant_stack/macro_shadow_eval_v1.sql with the schema-owner/admin role first."
    )
print("[PASS] macro shadow evaluation schema present")
PY

echo "[2/4] Selftest"
KALMAN_ENV_FILE="$ENV_FILE" "$RUN" selftest

echo "[3/4] Install systemd service/timer"
cat > /etc/systemd/system/kalman-macro-shadow-eval.service <<'EOF'
[Unit]
Description=Kalman Macro Shadow Evaluation V1
After=network-online.target kalman-macro-feature.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/kalman/app
Environment=KALMAN_ENV_FILE=/opt/kalman/.env
ExecStart=/opt/kalman/app/scripts/run_macro_shadow_eval_v1.sh sync
Nice=10
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > /etc/systemd/system/kalman-macro-shadow-eval.timer <<'EOF'
[Unit]
Description=Refresh Kalman macro shadow evaluation hourly

[Timer]
OnBootSec=17min
OnUnitActiveSec=1h
AccuracySec=2min
Persistent=true
Unit=kalman-macro-shadow-eval.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now kalman-macro-shadow-eval.timer

echo "[4/4] Installed"
systemctl list-timers --all 'kalman-macro-shadow-eval*' --no-pager || true
echo "Macro shadow evaluation installed. It remains research-only and does not alter R5.1 or trading."
