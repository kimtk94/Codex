#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo from the checked-out repository:" >&2
  echo "  sudo bash kalman-toss-gateway/scripts/deploy_macro_event_v17.sh" >&2
  exit 1
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE_DIR="/opt/kalman/state"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$STATE_DIR/macro-event-v17-backup-$STAMP"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "/opt/kalman/.env" ] || { echo "[FAIL] /opt/kalman/.env missing" >&2; exit 11; }

install -d -m 0750 "$STATE_DIR" "$BACKUP_DIR"
install -d -m 0755 "$APP_ROOT/engine" "$APP_ROOT/config" "$APP_ROOT/scripts"

FILES=(
  "engine/macro_consensus_provider_v1.py"
  "engine/macro_event_features_v1.py"
  "config/macro-event-features-v1.json"
  "config/macro-event-features-v1.cron.d"
  "scripts/run_macro_event_features_v1.sh"
  "scripts/install_macro_event_cron_v1.sh"
)

echo "[1/5] Validate source files"
for rel in "${FILES[@]}"; do
  [ -f "$SRC_ROOT/$rel" ] || { echo "[FAIL] source missing: $SRC_ROOT/$rel" >&2; exit 12; }
done

echo "[2/5] Backup current runtime macro files"
for rel in "${FILES[@]}"; do
  if [ -f "$APP_ROOT/$rel" ]; then
    install -D -m 0644 "$APP_ROOT/$rel" "$BACKUP_DIR/$rel"
  fi
done
echo "[INFO] backup=$BACKUP_DIR"

echo "[3/5] Install macro runtime files only"
install -m 0644 "$SRC_ROOT/engine/macro_consensus_provider_v1.py" "$APP_ROOT/engine/macro_consensus_provider_v1.py"
install -m 0644 "$SRC_ROOT/engine/macro_event_features_v1.py" "$APP_ROOT/engine/macro_event_features_v1.py"
install -m 0644 "$SRC_ROOT/config/macro-event-features-v1.json" "$APP_ROOT/config/macro-event-features-v1.json"
install -m 0644 "$SRC_ROOT/config/macro-event-features-v1.cron.d" "$APP_ROOT/config/macro-event-features-v1.cron.d"
install -m 0755 "$SRC_ROOT/scripts/run_macro_event_features_v1.sh" "$APP_ROOT/scripts/run_macro_event_features_v1.sh"
install -m 0755 "$SRC_ROOT/scripts/install_macro_event_cron_v1.sh" "$APP_ROOT/scripts/install_macro_event_cron_v1.sh"

echo "[4/5] Compile + selftest"
PYTHONPATH="$APP_ROOT" "$PY" -m py_compile   "$APP_ROOT/engine/macro_consensus_provider_v1.py"   "$APP_ROOT/engine/macro_event_features_v1.py"
KALMAN_ENV_FILE=/opt/kalman/.env "$APP_ROOT/scripts/run_macro_event_features_v1.sh" selftest

echo "[5/5] Migrate scheduler to cron"
"$APP_ROOT/scripts/install_macro_event_cron_v1.sh"

echo
echo "===== MACRO CRON ====="
cat /etc/cron.d/kalman-macro-feature
echo
echo "===== LEGACY TIMER ====="
systemctl is-enabled kalman-macro-feature.timer 2>/dev/null || true
systemctl is-active kalman-macro-feature.timer 2>/dev/null || true
echo
echo "Deployment complete. Trading gates and /opt/kalman/.env were not modified."
