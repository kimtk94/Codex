#!/usr/bin/env bash
# Manual mirror-only promotion. No LIVE order, risk, cron, or env changes.
# Run with --apply as root only after reviewing the associated PR.
set -uo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE_ROOT="${KALMAN_STATE_ROOT:-/opt/kalman/state}"
MODE="${1:-check}"
FILES=(trade_mirror.py trade_mirror_accounting.py)

if [[ ! -x "$PY" ]]; then
  echo "[FAIL] Python environment not available: $PY" >&2
  exit 2
fi
for f in "${FILES[@]}"; do
  if [[ ! -r "$SRC_ROOT/engine/$f" ]]; then
    echo "[FAIL] Missing source $f" >&2
    exit 2
  fi
done
if ! "$PY" -m py_compile "$SRC_ROOT/engine/trade_mirror.py" "$SRC_ROOT/engine/trade_mirror_accounting.py"; then
  echo "[FAIL] Python compilation failed" >&2
  exit 2
fi
if ! env PYTHONPATH="$SRC_ROOT" "$PY" -m unittest discover \
  -s "$SRC_ROOT/tests" -p test_trade_mirror_accounting.py -q; then
  echo "[FAIL] Accounting regression tests failed" >&2
  exit 2
fi
echo "[PASS] Source compilation and offline accounting tests"
if [[ "$MODE" != "--apply" ]]; then
  echo "[CHECK ONLY] No files installed. For controlled promotion: sudo bash $0 --apply"
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[FAIL] Root required for explicit --apply" >&2
  exit 3
fi
if [[ ! -d "$APP_ROOT/engine" || ! -f "$APP_ROOT/engine/trade_mirror.py" ]]; then
  echo "[FAIL] Existing deployed engine missing" >&2
  exit 3
fi
if [[ ! -d "$STATE_ROOT" ]]; then
  echo "[FAIL] State root missing" >&2
  exit 3
fi

# Prevent concurrent execution_watch code import during the short copy window.
exec 9>"$STATE_ROOT/auto-trade.lock"
if ! flock -n 9; then
  echo "[FAIL] Execution lock busy; no live files changed" >&2
  exit 4
fi
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$STATE_ROOT/trade-mirror-backup-$STAMP"
if ! mkdir -m 0700 "$BACKUP"; then
  echo "[FAIL] Cannot create backup" >&2
  exit 5
fi
for f in "${FILES[@]}"; do
  if [[ -f "$APP_ROOT/engine/$f" ]]; then
    if ! cp -a "$APP_ROOT/engine/$f" "$BACKUP/$f"; then
      echo "[FAIL] Backup failed; no files installed" >&2
      exit 5
    fi
  else
    : >"$BACKUP/$f.absent"
  fi
done

rollback() {
  local f
  for f in "${FILES[@]}"; do
    if [[ -f "$BACKUP/$f" ]]; then
      cp -a "$BACKUP/$f" "$APP_ROOT/engine/$f" || true
    elif [[ -e "$BACKUP/$f.absent" ]]; then
      rm -f "$APP_ROOT/engine/$f" || true
    fi
  done
}

for f in "${FILES[@]}"; do
  if ! install -o root -g root -m 0644 "$SRC_ROOT/engine/$f" "$APP_ROOT/engine/$f"; then
    echo "[FAIL] Install failed; restoring prior code" >&2
    rollback
    exit 6
  fi
done
if ! env PYTHONPATH="$APP_ROOT" "$PY" -c "import engine.trade_mirror; import engine.trade_mirror_accounting"; then
  echo "[FAIL] Deployed import failed; restoring prior code" >&2
  rollback
  exit 7
fi

echo "[PASS] Deployed trade mirror accounting ONLY"
echo "[INFO] Backup: $BACKUP"
echo "[INFO] Cron/environment/trading order logic unchanged"
echo "[INFO] Broker/Neon mirror sync NOT executed by this script"
echo "[INFO] Audit mirror after its next scheduled run before trusting net PnL"
