#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"

echo "===== R7.1 ACTUAL + SESSION REACTION ABLATION ====="
echo "app_root=$APP_ROOT"
echo "data_root=$ROOT"
echo "research_only=true"
echo "live_change=false"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r7_1_macro_ablation.py" \
  --root "$ROOT" \
  --bootstrap "${R7_BOOTSTRAP_REPS:-2000}"
