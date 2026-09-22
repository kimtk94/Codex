#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
MODE="${1:-smoke}"

case "$MODE" in
  smoke|recent) ;;
  *) echo "[FAIL] usage: $0 [smoke|recent]" >&2; return 2 2>/dev/null || exit 2 ;;
esac

echo "===== R9 NEWS PIT READINESS ====="
echo "mode=$MODE"
echo "research_only=true"
echo "production_changed=false"
echo "api_key_required=NONE"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r9_news_pit_readiness.py" \
  --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}" \
  --r8-manifest "${R9_R8_MANIFEST:-/opt/kalman/state/r8_sec/manifest.json}" \
  --output-dir "${R9_NEWS_OUT:-/opt/kalman/state/r9_news_pit}" \
  --mode "$MODE" \
  --min-request-interval "${R9_GDELT_REQUEST_INTERVAL:-8.0}"
