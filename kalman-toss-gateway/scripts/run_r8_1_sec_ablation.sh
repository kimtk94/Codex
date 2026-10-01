#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"

echo "===== R8.1 SEC CORPORATE EVENT ABLATION ====="
echo "research_only=true"
echo "live_change=false"
echo "candidate=R8C1_SEC_CORPORATE_EVENT"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r8_1_sec_ablation.py" \
  --root "$ROOT" \
  --events "${R8_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}" \
  --sec-manifest "${R8_SEC_MANIFEST:-/opt/kalman/state/r8_sec/manifest.json}" \
  --bootstrap "${R8_BOOTSTRAP_REPS:-2000}"
