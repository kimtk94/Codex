#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ROOT="${KALMAN_DATA_ROOT:-/mnt/gdrive}"
OUT="${R5_EXIT_SHADOW_OUT:-/mnt/gdrive/US_ETF/model_lab_v1/results/r5_exit_shadow_v1}"

echo "===== R5 EXIT SHADOW V1 ====="
echo "prospective_start=2026-09-22T10:45:00Z"
echo "horizons=2,4,6,8"
echo "production_changed=false"
echo "live_exit_changed=false"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r5_exit_shadow_v1.py" \
  --root "$ROOT" \
  --output-dir "$OUT"
