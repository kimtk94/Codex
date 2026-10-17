#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${1:-$BASE/config/multi_organ_aging.json}"
SRC="$BASE/src"
DEFAULT_VENV="/srv/is-analysis/.venvs/multi_organ_aging/bin/python"
if [ -x "$DEFAULT_VENV" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_VENV}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
export PYTHONPATH="$SRC:${PYTHONPATH:-}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

echo "===================================================="
echo "MULTI-ORGAN AGING PIPELINE"
echo "BASE=$BASE"
echo "CONFIG=$CONFIG"
echo "PYTHON_BIN=$PYTHON_BIN"
echo "===================================================="

FAILED=0

run_stage() {
  NAME="$1"
  shift
  echo
  echo "===== $NAME ====="
  "$@"
  RC=$?
  echo "[$NAME] rc=$RC"
  if [ "$RC" -ne 0 ]; then
    FAILED=1
  fi
  return "$RC"
}

run_stage "STAGE0_AUDIT" "$PYTHON_BIN" "$SRC/stage0_audit.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 0 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE1_LONGITUDINAL" "$PYTHON_BIN" "$SRC/stage1_build_longitudinal.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 1 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE2_CLOCKS" "$PYTHON_BIN" "$SRC/stage2_train_organ_clocks.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 2 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE2B_CROSSFIT" "$PYTHON_BIN" "$SRC/stage2b_crossfit_longitudinal.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 2B cross-fit failed; dependent longitudinal stages are not started."
  exit 1
fi

CROSSFIT_SCORES="/srv/is-analysis/results/multi_organ_aging/stage2b_crossfit/ORGAN_AGE_SCORES_LONG_CROSSFIT.tsv.gz"

run_stage "STAGE3_PACE" "$PYTHON_BIN" "$SRC/stage3_estimate_pace.py" --config "$CONFIG" --scores "$CROSSFIT_SCORES"
if [ "$?" -ne 0 ]; then
  echo "Stage 3 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE3B_LANDMARK_PACE" "$PYTHON_BIN" "$SRC/stage3b_landmark_pace.py" --config "$CONFIG" --scores "$CROSSFIT_SCORES"
run_stage "STAGE4_DISCORDANCE" "$PYTHON_BIN" "$SRC/stage4_discordance.py" --config "$CONFIG"
run_stage "STAGE5_PUBLIC_LANDMARK" "$PYTHON_BIN" "$SRC/stage5_public_landmark.py" --config "$CONFIG"
run_stage "STAGE5_OUTCOMES" "$PYTHON_BIN" "$SRC/stage5_outcomes.py" --config "$CONFIG"
run_stage "STAGE6_GENETICS" "$PYTHON_BIN" "$SRC/stage6_genetics.py" --config "$CONFIG"
run_stage "STAGE8_SENSITIVITY" "$PYTHON_BIN" "$SRC/stage8_sensitivity.py" --config "$CONFIG"
run_stage "STAGE7_INTEGRATE" "$PYTHON_BIN" "$SRC/stage7_integrate.py" --config "$CONFIG"

echo
echo "===================================================="
if [ "$FAILED" -eq 0 ]; then
  echo "PIPELINE STATUS: SUCCESS"
else
  echo "PIPELINE STATUS: PARTIAL/FAILED - review stage return codes above"
fi
echo "===================================================="
exit "$FAILED"
