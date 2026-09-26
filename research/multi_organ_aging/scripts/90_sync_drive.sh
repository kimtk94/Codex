#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

PROJECT="/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging"
RESULTS="/srv/is-analysis/results/multi_organ_aging"
REMOTE="gdrive:IS_Analysis_V3/MULTI_ORGAN_AGING"

echo "===== SYNC MASTER / CODE ====="
rclone copyto "$PROJECT/MULTI_ORGAN_AGING_MASTER.md" "$REMOTE/00_MASTER/MULTI_ORGAN_AGING_MASTER.md" --progress
RC0=$?

rclone copy "$PROJECT" "$REMOTE/02_CODE"   --exclude '.git/**'   --exclude '__pycache__/**'   --exclude '*.pyc'   --progress
RC1=$?

echo
echo "===== SYNC RESULTS ====="
rclone copy "$RESULTS" "$REMOTE/03_RESULTS"   --exclude '*.joblib'   --exclude '*.pkl'   --progress
RC2=$?

echo
echo "master_rc=$RC0 code_rc=$RC1 results_rc=$RC2"

if [ "$RC0" -ne 0 ] || [ "$RC1" -ne 0 ] || [ "$RC2" -ne 0 ]; then
  exit 1
fi

echo "===== SYNC COMPLETE ====="
