#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$SCRIPT_ROOT}"
VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PYTHON="${KALMAN_SYSTEM_PYTHON:-python3}"
REQ="$APP_ROOT/research/market_tools/requirements.txt"

[ -f "$REQ" ] || { echo "[FAIL] Research requirements missing: $REQ" >&2; exit 10; }

case "$VENV" in
  /opt/*)
    [ "$(id -u)" -eq 0 ] || {
      echo "Run with sudo or override KALMAN_RESEARCH_V2_VENV." >&2
      exit 11
    }
    ;;
esac

"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip wheel
"$VENV/bin/pip" install -r "$REQ"

printf '\nInstalled isolated Kalman research environment.\n'
printf 'Venv: %s\n' "$VENV"
printf 'Production and Market Data V2 venvs were not modified.\n'
