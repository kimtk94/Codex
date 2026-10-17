#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

PROJECT="/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging"
CONFIG="$PROJECT/config/multi_organ_aging.json"

echo "============================================================"
echo "MULTI-ORGAN AGING — FULL RUN"
echo "PROJECT=$PROJECT"
echo "CONFIG=$CONFIG"
echo "============================================================"

cd "$PROJECT" || exit 1

bash scripts/00_init_project.sh
RC_INIT=$?
if [ "$RC_INIT" -ne 0 ]; then
  echo "[FAILED] init rc=$RC_INIT"
  exit "$RC_INIT"
fi

bash scripts/run_pipeline.sh "$CONFIG"
RC_PIPE=$?

echo
echo "============================================================"
echo "init_rc=$RC_INIT pipeline_rc=$RC_PIPE"
echo "============================================================"

exit "$RC_PIPE"
