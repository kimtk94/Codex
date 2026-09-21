#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo /opt/kalman/app/scripts/install_macro_event_cron_v1.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RUN="$APP_ROOT/scripts/run_macro_event_features_v1.sh"
SOURCE_CRON="$APP_ROOT/config/macro-event-features-v1.cron.d"
TARGET_CRON="/etc/cron.d/kalman-macro-feature"
LOG_DIR="/opt/kalman/logs"

[ -x "$RUN" ] || chmod +x "$RUN"
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$SOURCE_CRON" ] || { echo "[FAIL] cron source missing: $SOURCE_CRON" >&2; exit 12; }

echo "[1/4] Macro feature selftest"
KALMAN_ENV_FILE="$ENV_FILE" "$RUN" selftest

echo "[2/4] Disable legacy systemd timer to prevent duplicate 15-minute runs"
if systemctl list-unit-files kalman-macro-feature.timer --no-legend 2>/dev/null | grep -q 'kalman-macro-feature.timer'; then
  systemctl disable --now kalman-macro-feature.timer || true
fi

echo "[3/4] Install dedicated cron"
install -d -m 0750 "$LOG_DIR"
install -m 0644 "$SOURCE_CRON" "$TARGET_CRON"

if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
else
  echo "[WARN] cron/crond service was not detected; inspect scheduler manually." >&2
fi

echo "[4/4] Installed"
cat "$TARGET_CRON"
echo
echo "Macro feature cron installed. KALMAN_MACRO_FEATURES_ENABLED and"
echo "KALMAN_MACRO_CONSENSUS_ENABLED remain controlled by /opt/kalman/.env."
echo "No trading gate was changed."
