#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/install_r5_exit_shadow_cron.sh" >&2
  exit 1
fi

BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
SRC="$APP_ROOT/config/r5-exit-shadow-v1.cron.d"
DST="/etc/cron.d/kalman-r5-exit-shadow-v1"
RUNNER="$APP_ROOT/scripts/run_r5_exit_shadow_v1.sh"
ENGINE="$APP_ROOT/research/r5_exit_shadow_v1.py"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
ok(){ echo "[OK]   $*"; }

[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -x "$PY" ] || fail "Python missing: $PY"
[ -f "$SRC" ] || fail "cron source missing: $SRC"
[ -f "$RUNNER" ] || fail "runner missing: $RUNNER"
[ -f "$ENGINE" ] || fail "engine missing: $ENGINE"

bash -n "$RUNNER" || fail "runner shell syntax invalid"
"$PY" -m py_compile "$ENGINE" || fail "exit-shadow Python compile failed"

grep -q '^CRON_TZ=Asia/Seoul$' "$SRC" || fail "CRON_TZ missing"
count="$(grep -Ec '^[0-9].*run_r5_exit_shadow_v1.sh' "$SRC" || true)"
[ "$count" -eq 1 ] || fail "expected exactly one active exit-shadow cron line, found $count"
grep -q '^15 8 \* \* 2-6 root ' "$SRC" || fail "expected Tue-Sat 08:15 KST schedule"

if grep -Eq 'auto_trade|position_manager|execute_order|Toss' "$SRC"; then
  fail "research cron must not invoke trading execution"
fi

systemctl is-active --quiet kalman-gdrive.service || fail "kalman-gdrive.service is not active"
mountpoint -q /mnt/gdrive || fail "/mnt/gdrive is not mounted"
timeout 20 ls /mnt/gdrive/US_ETF >/dev/null || fail "US_ETF root unreadable"

install -d -m 0755 "$BASE/logs"
install -m 0644 "$SRC" "$DST"

if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
else
  fail "cron/crond service not found"
fi

echo
echo "Installed $DST"
cat "$DST"
echo
echo "TRADING_ENABLED was not changed."
echo "AUTO_TRADE_ENABLED was not changed."
echo "R5 LIVE max-hold remains unchanged."
