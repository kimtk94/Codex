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
    "35 23 * * 1-5 root /opt/kalman/app/scripts/run_us_cycle.sh",
    "35 0-4 * * 2-6 root /opt/kalman/app/scripts/run_us_cycle.sh",
    "*/5 23 * * 1-5 root /opt/kalman/app/scripts/run_execution_watch.sh",
    "*/5 0-5 * * 2-6 root /opt/kalman/app/scripts/run_execution_watch.sh",
]
forbidden = [
    "run_pipeline.sh US",
    "run_auto_trade.sh",
]
missing = [line for line in required if line not in text]
if missing:
    raise SystemExit(f"US cycle cron contract failed: missing={missing}")
bad = [token for token in forbidden if token in text]
if bad:
    raise SystemExit(f"US cycle cron contract failed: independent workers remain={bad}")
print("[PASS] US hourly model cycle + 5m execution watcher cron contract")
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

grep -F "run_us_cycle.sh" /etc/cron.d/kalman >/dev/null
grep -F "run_execution_watch.sh" /etc/cron.d/kalman >/dev/null
! grep -F "run_pipeline.sh US" /etc/cron.d/kalman >/dev/null
! grep -F "run_auto_trade.sh" /etc/cron.d/kalman >/dev/null
systemctl is-active --quiet cron.service 2>/dev/null || systemctl is-active --quiet crond.service

echo
echo "KALMAN_LIVE_CANARY_5000_APPLIED"
echo "strategy=R5.1_BASE_HGB"
echo "signal_policy=R5_LIVE_TOP1"
echo "research_non_overlap=BENCHMARK_ONLY"
echo "entry=FIXED_KRW_5000"
echo "max_entries_per_symbol=3"
echo "add_on_min_bucket_gap=1"
echo "max_symbol_notional_krw=15000"
echo "max_active_positions=3"
echo "stop_loss=-3%"
echo "take_profit=+20%"
echo "model_rotation=disabled_for_multi_position"
echo "max_hold=4 canonical buckets"
echo "daily_buy_cap_krw=DISABLED_CASH_DRIVEN"
echo "cron=/etc/cron.d/kalman"
echo "us_cycle_kst=23:35_and_00:35-04:35"
echo "us_cycle_order=PIPELINE_COMMIT_THEN_AUTO_TRADE"
echo "execution_watch_kst=EVERY_5M_23:00-05:55"
echo "execution_watch_order=POSITION_MANAGER_THEN_AUTO_TRADE_THEN_MIRROR"
echo "execution_watch_model_refresh=DISABLED"
echo "us_signal_timestamp=60M_BAR_START"
echo "us_signal_freshness_basis=BAR_START_PLUS_60M"
echo "backup=$BACKUP"
echo "env_backup=$ENV_BACKUP"
