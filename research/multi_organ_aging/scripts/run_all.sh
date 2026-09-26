#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

PROJECT="/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging"
cd "$PROJECT" || exit 1

run_step () {
  echo
  echo "============================================================"
  echo "RUN: $*"
  echo "============================================================"
  "$@"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "[FAILED] rc=$RC :: $*"
    exit "$RC"
  fi
}

run_step bash scripts/00_init_project.sh
run_step python3 scripts/01_audit_koges.py
run_step python3 scripts/02_build_longitudinal_panel.py
run_step python3 scripts/03_fit_organ_age_models.py
run_step python3 scripts/04_estimate_aging_pace.py
run_step python3 scripts/05_multi_organ_patterns.py
run_step python3 scripts/06_define_outcomes.py
run_step python3 scripts/07_association_models.py
run_step python3 scripts/08_genetics_bridge.py
run_step python3 scripts/09_build_summary.py

echo
echo "ALL STAGES COMPLETED"
