#!/usr/bin/env bash

if [ "$(id -u)" -ne 0 ]; then
  echo "root privileges required: sudo bash scripts/deploy_execution_cost_calibrator.sh" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${APP}.execution-cost-backup.${STAMP}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] missing python: $PY" >&2
  exit 2
fi
if [ ! -d "$APP/engine" ] || [ ! -d "$APP/scripts" ]; then
  echo "[FAIL] production app layout missing: $APP" >&2
  exit 3
fi

python3 -m py_compile "$SRC/engine/execution_cost_calibrator.py"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] source calibrator compile rc=$RC" >&2
  exit "$RC"
fi

bash -n "$SRC/scripts/run_execution_watch.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] source execution watcher syntax rc=$RC" >&2
  exit "$RC"
fi
bash -n "$SRC/scripts/run_auto_trade.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] source auto trade syntax rc=$RC" >&2
  exit "$RC"
fi

mkdir -p "$BACKUP/engine" "$BACKUP/scripts"
if [ -f "$APP/engine/execution_cost_calibrator.py" ]; then
  cp -a "$APP/engine/execution_cost_calibrator.py" "$BACKUP/engine/"
fi
cp -a "$APP/scripts/run_execution_watch.sh" "$BACKUP/scripts/"
cp -a "$APP/scripts/run_auto_trade.sh" "$BACKUP/scripts/"

install -m 0644 "$SRC/engine/execution_cost_calibrator.py" "$APP/engine/execution_cost_calibrator.py"
install -m 0755 "$SRC/scripts/run_execution_watch.sh" "$APP/scripts/run_execution_watch.sh"
install -m 0755 "$SRC/scripts/run_auto_trade.sh" "$APP/scripts/run_auto_trade.sh"

"$PY" -m py_compile "$APP/engine/execution_cost_calibrator.py"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] deployed calibrator compile rc=$RC" >&2
  exit "$RC"
fi
bash -n "$APP/scripts/run_execution_watch.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] deployed execution watcher syntax rc=$RC" >&2
  exit "$RC"
fi
bash -n "$APP/scripts/run_auto_trade.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] deployed auto trade syntax rc=$RC" >&2
  exit "$RC"
fi

grep -F 'engine.execution_cost_calibrator' "$APP/scripts/run_execution_watch.sh" >/dev/null
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] watcher calibrator hook missing" >&2
  exit "$RC"
fi

KALMAN_ENV_FILE="$ENV_FILE" "$PY" -m engine.execution_cost_calibrator
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[WARN] initial calibration run failed rc=$RC; deployment files remain installed" >&2
fi

echo "EXECUTION_COST_CALIBRATOR_DEPLOYED"
echo "backup=$BACKUP"
echo "output=/opt/kalman/state/execution-cost-calibration.json"
exit 0
