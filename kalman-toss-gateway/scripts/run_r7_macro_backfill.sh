#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
MODE="${1:-smoke}"

case "$MODE" in
  smoke)
    exec bash "$APP_ROOT/scripts/run_r7_macro_free.sh" smoke
    ;;
  dry-run|full)
    exec bash "$APP_ROOT/scripts/run_r7_macro_free.sh" full
    ;;
  write)
    echo "[BLOCKED] Free R7 macro path is research-only and does not write to Neon." >&2
    echo "[BLOCKED] Revised BLS history is not PIT-vintage verified." >&2
    exit 3
    ;;
  *)
    echo "Usage: $0 {smoke|dry-run|full}" >&2
    exit 64
    ;;
esac
