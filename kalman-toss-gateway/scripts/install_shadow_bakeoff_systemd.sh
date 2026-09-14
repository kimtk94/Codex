#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
SERVICE_SRC="$APP_ROOT/config/kalman-shadow-bakeoff-daily.service"
TIMER_SRC="$APP_ROOT/config/kalman-shadow-bakeoff-daily.timer"
SERVICE_DST="/etc/systemd/system/kalman-shadow-bakeoff-daily.service"
TIMER_DST="/etc/systemd/system/kalman-shadow-bakeoff-daily.timer"
LEGACY_CRON="/etc/cron.d/kalman-shadow-bakeoff-v1"
ACTION="${1:---install}"

usage() {
  cat <<'EOF'
Usage:
  install_shadow_bakeoff_systemd.sh --install
  install_shadow_bakeoff_systemd.sh --remove
  install_shadow_bakeoff_systemd.sh --show
EOF
}

case "$ACTION" in
  --install|--remove|--show) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "[FAIL] unknown action: $ACTION" >&2; usage >&2; exit 2 ;;
esac

if [ "$ACTION" = "--show" ]; then
  systemctl status kalman-shadow-bakeoff-daily.timer --no-pager || true
  echo
  systemctl list-timers kalman-shadow-bakeoff-daily.timer --all --no-pager || true
  exit 0
fi

[ "$(id -u)" -eq 0 ] || {
  echo "[FAIL] must run as root" >&2
  exit 10
}

if [ "$ACTION" = "--remove" ]; then
  systemctl disable --now kalman-shadow-bakeoff-daily.timer >/dev/null 2>&1 || true
  rm -f "$SERVICE_DST" "$TIMER_DST"
  systemctl daemon-reload
  echo "REMOVED kalman-shadow-bakeoff-daily systemd units"
  exit 0
fi

for f in "$SERVICE_SRC" "$TIMER_SRC"   "$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"   "$APP_ROOT/scripts/run_historical_source_refresh_rclone.sh"
do
  [ -f "$f" ] || {
    echo "[FAIL] missing required file: $f" >&2
    exit 11
  }
done

if [ -f "$LEGACY_CRON" ]; then
  mv "$LEGACY_CRON" "$LEGACY_CRON.disabled.$(date -u +%Y%m%dT%H%M%SZ)"
fi

install -o root -g root -m 0644 "$SERVICE_SRC" "$SERVICE_DST"
install -o root -g root -m 0644 "$TIMER_SRC" "$TIMER_DST"
chmod 0755 "$APP_ROOT/scripts/run_historical_source_refresh_rclone.sh"

systemctl daemon-reload
systemctl enable --now kalman-shadow-bakeoff-daily.timer

echo "INSTALLED kalman-shadow-bakeoff-daily.timer"
systemctl list-timers kalman-shadow-bakeoff-daily.timer --all --no-pager
