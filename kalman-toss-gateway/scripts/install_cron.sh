#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run with sudo: sudo bash scripts/install_cron.sh' >&2
  exit 1
fi
BASE="${KALMAN_BASE:-/opt/kalman}"
APP_ROOT="${KALMAN_APP_ROOT:-$BASE/app}"
ENV_FILE="${KALMAN_ENV_FILE:-$BASE/.env}"
PY="${KALMAN_PYTHON:-$BASE/.venv/bin/python}"
STAMP="$BASE/state/smoke.ok"
FORCE="${1:-}"

"$APP_ROOT/scripts/preflight.sh"

DATA_ROOT="$($PY - <<'PY'
import os
from dotenv import dotenv_values
v = dotenv_values(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env'))
print(v.get('KALMAN_DATA_ROOT') or '/opt/kalman/data')
PY
)"

case "$DATA_ROOT" in
  /mnt/gdrive|/mnt/gdrive/*)
    if ! systemctl is-active --quiet kalman-gdrive.service; then
      echo 'Refusing cron install: kalman-gdrive.service is not active.' >&2
      exit 4
    fi
    if ! mountpoint -q /mnt/gdrive; then
      echo 'Refusing cron install: /mnt/gdrive is not mounted.' >&2
      exit 5
    fi
    if ! timeout 20 ls "$DATA_ROOT" >/dev/null; then
      echo "Refusing cron install: Drive data root is unreadable: $DATA_ROOT" >&2
      exit 6
    fi
    ;;
esac

if [ "$FORCE" != "--force" ]; then
  if [ ! -f "$STAMP" ]; then
    echo "Refusing cron install: $STAMP is missing." >&2
    echo 'Run: sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines' >&2
    exit 2
  fi
  now="$(date +%s)"
  stamp_mtime="$(stat -c %Y "$STAMP")"
  age=$((now - stamp_mtime))
  if [ "$age" -gt 86400 ]; then
    echo "Refusing cron install: smoke stamp is older than 24 hours ($age seconds)." >&2
    exit 3
  fi
fi

install -m 0644 "$APP_ROOT/config/kalman.cron.d" /etc/cron.d/kalman
if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
fi

echo 'Installed /etc/cron.d/kalman'
echo 'Trading remains controlled by /opt/kalman/.env; cron installation does not enable live trading.'
