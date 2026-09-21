#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/apply_live_canary_5000.sh" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${KALMAN_BASE:-/opt/kalman}"
APP="$BASE/app"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$BASE/app.stage.$STAMP"
BACKUP="$BASE/app.backup.$STAMP"
ENV_BACKUP="$BASE/state/live-canary-env-$STAMP.bak"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
install -d -m 0750 "$BASE/state"
cp -a "$ENV_FILE" "$ENV_BACKUP"
chmod 0600 "$ENV_BACKUP"

python3 -m py_compile \
  "$SRC/app/main.py" \
  "$SRC/app/managed_positions.py" \
  "$SRC/engine/auto_trade.py" \
  "$SRC/engine/position_manager.py" \
  "$SRC/engine/benchmark_ledger.py" \
  "$SRC/engine/trade_mirror.py"

rm -rf "$STAGE"
install -d -m 0755 "$STAGE"
cp -a "$SRC/app" "$SRC/engine" "$SRC/scripts" "$SRC/config" "$STAGE/"
if [ -d "$SRC/research" ]; then
  cp -a "$SRC/research" "$STAGE/"
fi
chmod +x "$STAGE/scripts/"*.sh

if [ -d "$APP" ]; then
  mv "$APP" "$BACKUP"
fi
mv "$STAGE" "$APP"

rollback() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ -f "$ENV_BACKUP" ]; then
      echo "[ROLLBACK] restoring previous /opt/kalman/.env" >&2
      cp -a "$ENV_BACKUP" "$ENV_FILE"
      chmod 0600 "$ENV_FILE"
    fi
    if [ -d "$BACKUP" ]; then
      echo "[ROLLBACK] restoring previous /opt/kalman/app" >&2
      rm -rf "$APP"
      mv "$BACKUP" "$APP"
    fi
    systemctl restart kalman-toss-gateway.service || true
  fi
  exit "$rc"
}
trap rollback ERR

# Close live entry gates while runtime and scheduler are being replaced.
KALMAN_ENV_FILE="$ENV_FILE" bash "$APP/scripts/configure_auto_trade_env.sh" off

install -m 0644 "$APP/config/kalman.cron.d" /etc/cron.d/kalman
if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
fi

python3 - <<'PY'
from pathlib import Path

text = Path("/etc/cron.d/kalman").read_text(encoding="utf-8")
required = [
    "35 22-23 * * 1-5 root /opt/kalman/app/scripts/run_pipeline.sh US",
    "15 0-6 * * 2-6 root /opt/kalman/app/scripts/run_pipeline.sh US",
    "45 22-23 * * 1-5 root /opt/kalman/app/scripts/run_auto_trade.sh",
    "25 0-6 * * 2-6 root /opt/kalman/app/scripts/run_auto_trade.sh",
]
missing = [line for line in required if line not in text]
if missing:
    raise SystemExit(f"US auto-trade cron contract failed: missing={missing}")
print("[PASS] US auto-trade cron contract")
PY

# Open the explicit LIVE canary gates only after the new runtime and cron validate.
KALMAN_ENV_FILE="$ENV_FILE" bash "$APP/scripts/configure_auto_trade_env.sh" live-canary-5000

systemctl restart kalman-toss-gateway.service
sleep 2
systemctl is-active --quiet kalman-toss-gateway.service
curl -fsS --max-time 10 http://127.0.0.1:8787/health >"$BASE/state/gateway-health-$STAMP.json"

export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP"

"$PY" -m engine.benchmark_ledger
"$PY" -m engine.trade_mirror
bash "$APP/scripts/trading_status.sh"

grep -F "run_auto_trade.sh" /etc/cron.d/kalman >/dev/null
grep -F "run_pipeline.sh US" /etc/cron.d/kalman >/dev/null
systemctl is-active --quiet cron.service 2>/dev/null || systemctl is-active --quiet crond.service

echo
echo "KALMAN_LIVE_CANARY_5000_APPLIED"
echo "strategy=R5.1_BASE_HGB"
echo "entry=FIXED_KRW_5000"
echo "stop_loss=-3%"
echo "take_profit=+20%"
echo "model_rotation=enabled"
echo "max_hold=4 canonical buckets"
echo "daily_buy_cap_krw=DISABLED_CASH_DRIVEN"
echo "cron=/etc/cron.d/kalman"
echo "us_open_pipeline_kst=22:35_or_23:35"
echo "us_open_trade_poll_kst=22:45_or_23:45"
echo "overnight_pipeline_kst=00:15-06:15"
echo "overnight_trade_poll_kst=00:25-06:25"
echo "backup=$BACKUP"
echo "env_backup=$ENV_BACKUP"
