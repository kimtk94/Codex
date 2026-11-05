#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
MODE="${1:-smoke}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "===== R7 FREE MACRO ====="
echo "mode=$MODE"
echo "api_keys_required=NONE"

case "$MODE" in
  smoke)
    "$PY" "$APP_ROOT/research/r7_macro_free_backfill.py" --start-year 2025 --end-year 2026
    ;;
  full)
    "$PY" "$APP_ROOT/research/r7_macro_free_backfill.py" --start-year 2020 --end-year 2026
    ;;
  *)
    echo "[FAIL] usage: $0 {smoke|full}" >&2
    return 64 2>/dev/null || exit 64
    ;;
esac
