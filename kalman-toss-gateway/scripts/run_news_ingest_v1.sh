#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
STATE_DIR="${KALMAN_NEWS_STATE_DIR:-/opt/kalman/state/news}"
SPOOL_DIR="${KALMAN_NEWS_SPOOL_DIR:-/var/lib/kalman/news}"

mkdir -p "$LOCK_DIR" "$STATE_DIR" "$SPOOL_DIR"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }
[ -f "$APP_ROOT/config/news-ingest-v1.json" ] || { echo "[FAIL] news config missing" >&2; exit 12; }

cmd="${1:-}"
case "$cmd" in
  collect|sync|coverage|enrich|import-gdelt-csv|selftest) ;;
  *) echo "Usage: $0 {collect|sync|coverage|enrich|import-gdelt-csv|selftest} [args...]" >&2; exit 2 ;;
esac

cd "$APP_ROOT"
exec flock -n "$LOCK_DIR/news-ingest-v1.lock" "$PY" -m engine.news_ingest_v1 "$@"
