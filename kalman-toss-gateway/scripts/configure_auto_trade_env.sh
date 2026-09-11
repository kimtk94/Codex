#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PROFILE="${1:-dry-run}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0 [dry-run|cash-fraction-dry-run|off]" >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 2
fi

case "$PROFILE" in
  dry-run)
    export CFG_AUTO_TRADE_ENABLED=true
    export CFG_AUTO_TRADE_EXECUTION_MODE=DRY_RUN
    export CFG_AUTO_TRADE_SIGNAL_POLICY=APPROVED_ONLY
    export CFG_AUTO_TRADE_SHADOW_CONFIRM=
    export CFG_AUTO_TRADE_REQUIRE_ACCOUNT_FLAT=true
    export CFG_AUTO_TRADE_DRY_RUN_MAX_SIGNAL_AGE_MINUTES=1440
    export CFG_AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES=90
    export CFG_AUTO_TRADE_SIZING_MODE=FIXED_USD
    export CFG_AUTO_TRADE_ORDER_USD=2
    export CFG_AUTO_TRADE_CASH_FRACTION=0.10
    export CFG_AUTO_TRADE_CASH_RESERVE_USD=0
    export CFG_AUTO_TRADE_MIN_ORDER_USD=1
    export CFG_AUTO_TRADE_MAX_ORDER_USD=2
    export CFG_TRADING_ENABLED=false
    export CFG_LIVE_TRADING_CONFIRM=
    ;;
  cash-fraction-dry-run)
    export CFG_AUTO_TRADE_ENABLED=true
    export CFG_AUTO_TRADE_EXECUTION_MODE=DRY_RUN
    export CFG_AUTO_TRADE_SIGNAL_POLICY=APPROVED_ONLY
    export CFG_AUTO_TRADE_SHADOW_CONFIRM=
    export CFG_AUTO_TRADE_REQUIRE_ACCOUNT_FLAT=true
    export CFG_AUTO_TRADE_DRY_RUN_MAX_SIGNAL_AGE_MINUTES=1440
    export CFG_AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES=90
    export CFG_AUTO_TRADE_SIZING_MODE=CASH_FRACTION
    export CFG_AUTO_TRADE_ORDER_USD=2
    export CFG_AUTO_TRADE_CASH_FRACTION="${AUTO_TRADE_CASH_FRACTION:-0.10}"
    export CFG_AUTO_TRADE_CASH_RESERVE_USD="${AUTO_TRADE_CASH_RESERVE_USD:-100}"
    export CFG_AUTO_TRADE_MIN_ORDER_USD="${AUTO_TRADE_MIN_ORDER_USD:-1}"
    export CFG_AUTO_TRADE_MAX_ORDER_USD="${AUTO_TRADE_MAX_ORDER_USD:-50}"
    export CFG_TRADING_ENABLED=false
    export CFG_LIVE_TRADING_CONFIRM=
    ;;
  off)
    export CFG_AUTO_TRADE_ENABLED=false
    export CFG_AUTO_TRADE_EXECUTION_MODE=DRY_RUN
    export CFG_AUTO_TRADE_SIGNAL_POLICY=APPROVED_ONLY
    export CFG_AUTO_TRADE_SHADOW_CONFIRM=
    export CFG_AUTO_TRADE_REQUIRE_ACCOUNT_FLAT=true
    export CFG_AUTO_TRADE_DRY_RUN_MAX_SIGNAL_AGE_MINUTES=1440
    export CFG_AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES=90
    export CFG_AUTO_TRADE_SIZING_MODE=FIXED_USD
    export CFG_AUTO_TRADE_ORDER_USD=2
    export CFG_AUTO_TRADE_CASH_FRACTION=0.10
    export CFG_AUTO_TRADE_CASH_RESERVE_USD=0
    export CFG_AUTO_TRADE_MIN_ORDER_USD=1
    export CFG_AUTO_TRADE_MAX_ORDER_USD=2
    export CFG_TRADING_ENABLED=false
    export CFG_LIVE_TRADING_CONFIRM=
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    echo "Usage: sudo $0 [dry-run|cash-fraction-dry-run|off]" >&2
    exit 3
    ;;
esac

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${ENV_FILE}.bak.${STAMP}"
cp -a "$ENV_FILE" "$BACKUP"
chmod 0600 "$BACKUP"

python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations
import os
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
keys = [
    'AUTO_TRADE_ENABLED',
    'AUTO_TRADE_EXECUTION_MODE',
    'AUTO_TRADE_SIGNAL_POLICY',
    'AUTO_TRADE_SHADOW_CONFIRM',
    'AUTO_TRADE_REQUIRE_ACCOUNT_FLAT',
    'AUTO_TRADE_DRY_RUN_MAX_SIGNAL_AGE_MINUTES',
    'AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES',
    'AUTO_TRADE_SIZING_MODE',
    'AUTO_TRADE_ORDER_USD',
    'AUTO_TRADE_CASH_FRACTION',
    'AUTO_TRADE_CASH_RESERVE_USD',
    'AUTO_TRADE_MIN_ORDER_USD',
    'AUTO_TRADE_MAX_ORDER_USD',
    'TRADING_ENABLED',
    'LIVE_TRADING_CONFIRM',
]
values = {k: os.environ[f'CFG_{k}'] for k in keys}

original = env_path.read_text(encoding='utf-8').splitlines()
out: list[str] = []
seen: set[str] = set()

for line in original:
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in line:
        out.append(line)
        continue
    key = line.split('=', 1)[0].strip()
    if key in values:
        if key not in seen:
            out.append(f'{key}={values[key]}')
            seen.add(key)
        continue
    out.append(line)

missing = [k for k in keys if k not in seen]
if missing:
    if out and out[-1] != '':
        out.append('')
    out.append('# --- Managed auto-trade settings ---')
    for key in missing:
        out.append(f'{key}={values[key]}')

text = '\n'.join(out).rstrip() + '\n'
tmp = env_path.with_suffix(env_path.suffix + '.tmp')
tmp.write_text(text, encoding='utf-8')
tmp.chmod(0o600)
tmp.replace(env_path)
env_path.chmod(0o600)
PY

printf 'Updated %s using profile: %s\n' "$ENV_FILE" "$PROFILE"
printf 'Backup: %s\n\n' "$BACKUP"

printf '%s\n' '--- auto-trade settings ---'
grep -E '^(AUTO_TRADE_|TRADING_ENABLED|LIVE_TRADING_CONFIRM)=' "$ENV_FILE" || true

printf '\n%s\n' 'Secrets and unrelated env values were preserved.'
printf '%s\n' 'LIVE trading remains disabled in every profile provided by this script.'
