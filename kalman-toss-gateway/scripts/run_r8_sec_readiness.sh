#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
R5_SCORED="${R8_R5_SCORED:-/mnt/gdrive/US_ETF/model_lab_v1/results/r5_0_1_research_sandbox_all_data/r5_0_1_scored_rows.parquet}"
OUT="${R8_SEC_OUT:-/opt/kalman/state/r8_sec}"

echo "===== R8 SEC CORPORATE EVENT READINESS ====="
echo "api_key_required=NONE"
echo "production_changed=false"
echo "r5_scored=$R5_SCORED"
echo "output=$OUT"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$PY" "$APP_ROOT/research/r8_sec_corporate_events.py" \
  --r5-scored "$R5_SCORED" \
  --output-dir "$OUT" \
  --start-year 2020 \
  --end-year 2026
