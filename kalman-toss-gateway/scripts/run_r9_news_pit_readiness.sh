#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
MODE="${1:-smoke}"

case "$MODE" in
  smoke|full) ;;
  *) echo "[FAIL] usage: $0 [smoke|full]" >&2; return 2 2>/dev/null || exit 2 ;;
esac

echo "===== R9 NEWS PIT READINESS ====="
echo "mode=$MODE"
echo "research_only=true"
echo "production_changed=false"
echo "api_key_required=NONE"

if [ "$MODE" = "smoke" ]; then
  INTERVAL="${R9_GDELT_REQUEST_INTERVAL:-20}"
  RETRIES="${R9_GDELT_MAX_RETRIES:-1}"
else
  if [ "${R9_ALLOW_LONG_FULL:-NO}" != "YES" ]; then
    echo "[BLOCKED] full ArticleList backfill is intentionally disabled: current design can take many hours." >&2
    echo "[BLOCKED] set R9_ALLOW_LONG_FULL=YES only after the historical source path is explicitly approved." >&2
    return 3 2>/dev/null || exit 3
  fi
  INTERVAL="${R9_GDELT_REQUEST_INTERVAL:-15}"
  RETRIES="${R9_GDELT_MAX_RETRIES:-3}"
fi

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r9_news_pit_readiness.py" \
  --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}" \
  --r8-manifest "${R9_R8_MANIFEST:-/opt/kalman/state/r8_sec/manifest.json}" \
  --output-dir "${R9_NEWS_OUT:-/opt/kalman/state/r9_news_pit}" \
  --cache-dir "${R9_NEWS_CACHE:-/opt/kalman/state/r9_news_pit/cache}" \
  --mode "$MODE" \
  --min-request-interval "$INTERVAL" \
  --min-window-hours "${R9_GDELT_MIN_WINDOW_HOURS:-24}" \
  --max-retries "$RETRIES"
