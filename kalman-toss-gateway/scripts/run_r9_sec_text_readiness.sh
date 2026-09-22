#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
OUT="${R9_SEC_TEXT_OUT:-/opt/kalman/state/r9_sec_text}"
CACHE="${R9_SEC_TEXT_CACHE:-/opt/kalman/state/r9_sec_text/cache}"

echo "===== R9 SEC TEXT READINESS ====="
echo "research_only=true"
echo "production_changed=false"
echo "api_key_required=NONE"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r9_sec_text_readiness.py" \
  --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}" \
  --r8-manifest "${R9_R8_MANIFEST:-/opt/kalman/state/r8_sec/manifest.json}" \
  --output-dir "$OUT" \
  --cache-dir "$CACHE" \
  --min-request-interval "${R9_SEC_REQUEST_INTERVAL:-0.35}"
