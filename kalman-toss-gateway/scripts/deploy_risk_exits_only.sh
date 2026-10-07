#!/usr/bin/env bash

if [ "$(id -u)" -ne 0 ]; then
  echo "root privileges required: sudo bash scripts/deploy_risk_exits_only.sh" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${APP}.risk-exits-only-backup.${STAMP}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] missing production python: $PY" >&2
  exit 2
fi
if [ ! -d "$APP/app" ] || [ ! -d "$APP/engine" ] || [ ! -d "$APP/scripts" ]; then
  echo "[FAIL] production app layout missing: $APP" >&2
  exit 3
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "[FAIL] env file missing: $ENV_FILE" >&2
  exit 4
fi

python3 -m py_compile \
  "$SRC/app/executor.py" \
  "$SRC/engine/auto_trade.py" \
  "$SRC/engine/r5_conditional_live.py" \
  "$SRC/engine/open_carry_live.py" \
  "$SRC/scripts/set_risk_exits_only.py"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] source compile rc=$RC" >&2
  exit "$RC"
fi

mkdir -p "$BACKUP/app" "$BACKUP/engine" "$BACKUP/scripts"
for f in \
  "$APP/app/executor.py" \
  "$APP/engine/auto_trade.py" \
  "$APP/engine/r5_conditional_live.py" \
  "$APP/engine/open_carry_live.py"; do
  if [ -f "$f" ]; then
    case "$f" in
      */app/*) cp -a "$f" "$BACKUP/app/" ;;
      */engine/*) cp -a "$f" "$BACKUP/engine/" ;;
    esac
  else
    echo "[INFO] no pre-existing file to back up: $f"
  fi
done
if [ -f "$APP/scripts/set_risk_exits_only.py" ]; then
  cp -a "$APP/scripts/set_risk_exits_only.py" "$BACKUP/scripts/"
fi

install -m 0644 "$SRC/app/executor.py" "$APP/app/executor.py"
install -m 0644 "$SRC/engine/auto_trade.py" "$APP/engine/auto_trade.py"
install -m 0644 "$SRC/engine/r5_conditional_live.py" "$APP/engine/r5_conditional_live.py"
install -m 0644 "$SRC/engine/open_carry_live.py" "$APP/engine/open_carry_live.py"
install -m 0644 "$SRC/scripts/set_risk_exits_only.py" "$APP/scripts/set_risk_exits_only.py"

"$PY" -m py_compile \
  "$APP/app/executor.py" \
  "$APP/engine/auto_trade.py" \
  "$APP/engine/r5_conditional_live.py" \
  "$APP/engine/open_carry_live.py" \
  "$APP/scripts/set_risk_exits_only.py"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] deployed compile rc=$RC" >&2
  exit "$RC"
fi

"$PY" "$APP/scripts/set_risk_exits_only.py" --env-file "$ENV_FILE"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] env switch rc=$RC" >&2
  exit "$RC"
fi

grep -q '^AUTO_TRADE_ENTRY_ENABLED=false$' "$ENV_FILE"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] entry-disable env verification" >&2
  exit "$RC"
fi
grep -q '^AUTO_TRADE_ENABLED=true$' "$ENV_FILE"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] position-manager enable verification" >&2
  exit "$RC"
fi
grep -q '^TRADING_ENABLED=true$' "$ENV_FILE"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] risk-exit live gate verification" >&2
  exit "$RC"
fi

echo "RISK_EXITS_ONLY_DEPLOYED"
echo "code_backup=$BACKUP"
echo "new_buys=BLOCKED"
echo "managed_risk_exits=ENABLED"
echo "open_carry_live=DISABLED"
exit 0
