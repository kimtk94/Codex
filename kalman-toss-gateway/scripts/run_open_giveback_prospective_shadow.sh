#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
cd "$APP_ROOT"
exec "$PY" -m research.quant_stack.open_giveback_prospective_shadow "$@"
