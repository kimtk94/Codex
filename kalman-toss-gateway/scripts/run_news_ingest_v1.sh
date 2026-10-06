#!/usr/bin/env bash
set -uo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
STATE_DIR="${KALMAN_NEWS_STATE_DIR:-/opt/kalman/state/news}"
SPOOL_DIR="${KALMAN_NEWS_SPOOL_DIR:-/var/lib/kalman/news}"

mkdir -p "$LOCK_DIR" "$STATE_DIR" "$SPOOL_DIR" || exit 13
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

cd "$APP_ROOT" || exit 14

# The collector, sync, and coverage timers intentionally share one state/spool.
# Timer alignment can therefore cause a normal lock collision. Use a dedicated
# lock-contention exit code so real Python failures remain visible to systemd.
flock -n -E 75 "$LOCK_DIR/news-ingest-v1.lock" "$PY" -m engine.news_ingest_v1 "$@"
rc=$?

if [ "$rc" -eq 75 ]; then
  echo "[NEWS][${cmd^^}] skipped: another news-ingest job holds the lock"
  exit 0
fi

exit "$rc"
