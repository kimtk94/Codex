#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"

mkdir -p "$LOCK_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$APP_ROOT/config/macro-event-features-v1.json" ] || {
  echo "[FAIL] macro feature config missing" >&2
  exit 12
}

cmd="${1:-}"
case "$cmd" in
  build|import-csv|import-policy-csv|status|selftest) ;;
  *)
    echo "Usage: $0 {build|import-csv|import-policy-csv|status|selftest} [args...]" >&2
    exit 2
    ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/macro-event-feature-v1.lock"   "$PY" -m engine.macro_event_features_v1 "$@"
