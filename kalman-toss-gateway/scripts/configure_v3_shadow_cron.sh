#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
CRON_FILE="${KALMAN_V3_CRON_FILE:-/etc/cron.d/kalman-v3-shadow}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"

if [ "$(id -u)" -ne 0 ]; then
  echo "[FAIL] configure_v3_shadow_cron.sh must run as root" >&2
  exit 10
fi

[ -x "$APP_ROOT/scripts/run_v3_shadow_cycle.sh" ] || {
  echo "[FAIL] cycle runner missing: $APP_ROOT/scripts/run_v3_shadow_cycle.sh" >&2
  exit 11
}

mkdir -p "$LOG_DIR" "$(dirname "$CRON_FILE")"

STAMP="$(date +%Y%m%d_%H%M%S)"
if [ -f "$CRON_FILE" ]; then
  cp -a "$CRON_FILE" "${CRON_FILE}.bak.${STAMP}"
fi

TMP="$(mktemp)"
cat >"$TMP" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=""
CRON_TZ=Asia/Seoul

# Kalman V3 frozen shadow-forward refresh.
# BTC: after UTC daily candle close (09:00 KST).
15 9 * * * root KALMAN_APP_ROOT=$APP_ROOT KALMAN_ENV_FILE=/opt/kalman/.env $APP_ROOT/scripts/run_v3_shadow_cycle.sh BTC >> $LOG_DIR/v3-shadow-btc.log 2>&1

# US: previous regular-session daily bar should be available by morning KST.
25 9 * * 1-5 root KALMAN_APP_ROOT=$APP_ROOT KALMAN_ENV_FILE=/opt/kalman/.env $APP_ROOT/scripts/run_v3_shadow_cycle.sh US >> $LOG_DIR/v3-shadow-us.log 2>&1

# KR: refresh after regular market close.
40 16 * * 1-5 root KALMAN_APP_ROOT=$APP_ROOT KALMAN_ENV_FILE=/opt/kalman/.env $APP_ROOT/scripts/run_v3_shadow_cycle.sh KR >> $LOG_DIR/v3-shadow-kr.log 2>&1
EOF

install -o root -g root -m 0644 "$TMP" "$CRON_FILE"
rm -f "$TMP"

echo "===== INSTALLED V3 SHADOW CRON ====="
cat "$CRON_FILE"
echo
echo "[PASS] V3 shadow cron installed"
echo "cron_file=$CRON_FILE"
echo "timezone=Asia/Seoul"
echo "BTC=09:15 daily"
echo "US=09:25 weekdays"
echo "KR=16:40 weekdays"
