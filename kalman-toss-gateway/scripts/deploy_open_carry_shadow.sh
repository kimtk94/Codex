#!/usr/bin/env bash

if [ "$(id -u)" -ne 0 ]; then
  echo "root privileges required" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${APP}.open-carry-backup.${STAMP}"

[ -d "$APP/engine" ] || { echo "[FAIL] missing $APP/engine" >&2; exit 2; }
[ -d "$APP/scripts" ] || { echo "[FAIL] missing $APP/scripts" >&2; exit 3; }
[ -x "$PY" ] || { echo "[FAIL] missing python $PY" >&2; exit 4; }

python3 -m py_compile "$SRC/engine/open_carry_shadow.py"
bash -n "$SRC/scripts/run_execution_watch.sh"

mkdir -p "$BACKUP/engine" "$BACKUP/scripts"
cp -a "$APP/scripts/run_execution_watch.sh" "$BACKUP/scripts/"
if [ -f "$APP/engine/open_carry_shadow.py" ]; then
  cp -a "$APP/engine/open_carry_shadow.py" "$BACKUP/engine/"
fi

install -m 0644 "$SRC/engine/open_carry_shadow.py" "$APP/engine/open_carry_shadow.py"
install -m 0755 "$SRC/scripts/run_execution_watch.sh" "$APP/scripts/run_execution_watch.sh"

"$PY" -m py_compile "$APP/engine/open_carry_shadow.py"
bash -n "$APP/scripts/run_execution_watch.sh"

grep -F 'engine.open_carry_shadow' "$APP/scripts/run_execution_watch.sh" >/dev/null
grep -F 'SHADOW_NO_BROKER_ORDERS' "$APP/engine/open_carry_shadow.py" >/dev/null

echo "OPEN_CARRY_SHADOW_DEPLOYED"
echo "target_total_krw=10000"
echo "chunk_krw=5000"
echo "evaluation_et=09:30,09:35,09:40"
echo "broker_orders=NONE"
echo "backup=$BACKUP"
