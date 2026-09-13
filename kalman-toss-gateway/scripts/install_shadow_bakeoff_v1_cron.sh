#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
CRON_FILE="/etc/cron.d/kalman-shadow-bakeoff-v1"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"
ACTION="${1:---install}"

usage() {
  cat <<'EOF'
Usage:
  install_shadow_bakeoff_v1_cron.sh --install
  install_shadow_bakeoff_v1_cron.sh --remove
  install_shadow_bakeoff_v1_cron.sh --show

Installs a file-only forward SHADOW bakeoff schedule.
No Neon write. No Toss execution. No live execution.
EOF
}

case "$ACTION" in
  --install|--remove|--show) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "[FAIL] Unknown action: $ACTION" >&2; usage >&2; exit 2 ;;
esac

RUNNER="$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"
[ -f "$RUNNER" ] || {
  echo "[FAIL] runner missing: $RUNNER" >&2
  exit 10
}

if [ "$ACTION" = "--show" ]; then
  if [ -f "$CRON_FILE" ]; then
    cat "$CRON_FILE"
  else
    echo "NOT_INSTALLED"
  fi
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "[FAIL] Must run as root because $CRON_FILE is system cron" >&2
  exit 11
fi

if [ "$ACTION" = "--remove" ]; then
  rm -f "$CRON_FILE"
  echo "REMOVED $CRON_FILE"
  exit 0
fi

mkdir -p "$LOG_DIR"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

cat > "$tmp" <<EOF
# Kalman Forward SHADOW Bake-off V1
# Installed by scripts/install_shadow_bakeoff_v1_cron.sh
# File-only / fail-closed / no production writes
CRON_TZ=Asia/Seoul
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Tue-Sat 08:10 KST, after the prior US close and before KR regular session.
# The runner first refreshes current V2 market/features, then checks whether
# historical integrated sources actually advanced past the fixed seed.
10 8 * * 2-6 root /bin/bash $RUNNER >> $LOG_DIR/shadow-bakeoff-v1.log 2>&1
EOF

install -o root -g root -m 0644 "$tmp" "$CRON_FILE"

echo "INSTALLED $CRON_FILE"
echo
cat "$CRON_FILE"
echo
echo "Safety:"
echo "  production_write = FALSE"
echo "  neon_write       = FALSE"
echo "  toss_execution   = FALSE"
echo "  live_execution   = FALSE"
echo
echo "Manual smoke:"
echo "  /bin/bash $RUNNER"
