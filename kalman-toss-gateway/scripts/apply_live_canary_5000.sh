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

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

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
  if [ "$rc" -ne 0 ] && [ -d "$BACKUP" ]; then
    echo "[ROLLBACK] restoring previous /opt/kalman/app" >&2
    rm -rf "$APP"
    mv "$BACKUP" "$APP"
    systemctl restart kalman-toss-gateway.service || true
  fi
  exit "$rc"
}
trap rollback ERR

KALMAN_ENV_FILE="$ENV_FILE" bash "$APP/scripts/configure_auto_trade_env.sh" live-canary-5000

install -m 0644 "$APP/config/kalman.cron.d" /etc/cron.d/kalman
if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
fi

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

echo
echo "KALMAN_LIVE_CANARY_5000_APPLIED"
echo "strategy=R5.1_BASE_HGB"
echo "entry=FIXED_KRW_5000"
echo "stop_loss=-3%"
echo "take_profit=+20%"
echo "model_rotation=enabled"
echo "max_hold=4 canonical buckets"
echo "daily_buy_cap_krw=30000"
echo "cron=/etc/cron.d/kalman"
echo "backup=$BACKUP"
