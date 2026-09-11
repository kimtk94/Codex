#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$SCRIPT_ROOT}"
VENV="${KALMAN_MARKET_V2_VENV:-/opt/kalman/.venv-market-v2}"
PYTHON="${KALMAN_SYSTEM_PYTHON:-python3}"
REQ="$APP_ROOT/engine/market_data/requirements.txt"

if [ ! -f "$REQ" ]; then
  echo "[FAIL] Market Tools V2 requirements missing: $REQ" >&2
  exit 10
fi

case "$VENV" in
  /opt/*)
    if [ "$(id -u)" -ne 0 ]; then
      echo "Default V2 venv is under /opt. Run with sudo or override KALMAN_MARKET_V2_VENV." >&2
      exit 11
    fi
    ;;
esac

"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -r "$REQ"

printf '\nInstalled isolated Kalman Market Tools V2 environment.\n'
printf 'Venv: %s\n' "$VENV"
printf 'Production /opt/kalman/.venv was not modified.\n'
printf 'Next: %s/scripts/run_market_data_v2.sh\n' "$APP_ROOT"
