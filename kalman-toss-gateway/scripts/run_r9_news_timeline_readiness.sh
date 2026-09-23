#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
MODE="${1:-smoke}"

case "$MODE" in
  smoke|full) ;;
  *) echo "[FAIL] usage: $0 [smoke|full]" >&2; return 2 2>/dev/null || exit 2 ;;
esac

echo "===== R9 NEWS TIMELINE READINESS ====="
echo "mode=$MODE"
echo "research_only=true"
echo "production_changed=false"
echo "source=GDELT_DOC_2_TIMELINEVOLRAW"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" "$APP_ROOT/research/r9_news_timeline_readiness.py" \
  --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}" \
  --r8-manifest "${R9_R8_MANIFEST:-/opt/kalman/state/r8_sec/manifest.json}" \
  --output-dir "${R9_TIMELINE_OUT:-/opt/kalman/state/r9_news_timeline}" \
  --cache-dir "${R9_TIMELINE_CACHE:-/opt/kalman/state/r9_news_timeline/cache}" \
  --mode "$MODE" \
  --min-request-interval "${R9_TIMELINE_REQUEST_INTERVAL:-12}" \
  --max-retries "${R9_TIMELINE_MAX_RETRIES:-2}"
