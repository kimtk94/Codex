#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${1:-$BASE/config/multi_organ_aging.json}"
SRC="$BASE/src"
export PYTHONPATH="$SRC:${PYTHONPATH:-}"

echo "===================================================="
echo "MULTI-ORGAN AGING PIPELINE"
echo "BASE=$BASE"
echo "CONFIG=$CONFIG"
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

run_stage "STAGE0_AUDIT" python3 "$SRC/stage0_audit.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 0 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE1_LONGITUDINAL" python3 "$SRC/stage1_build_longitudinal.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 1 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE2_CLOCKS" python3 "$SRC/stage2_train_organ_clocks.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 2 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE3_PACE" python3 "$SRC/stage3_estimate_pace.py" --config "$CONFIG"
if [ "$?" -ne 0 ]; then
  echo "Stage 3 failed; dependent stages are not started."
  exit 1
fi

run_stage "STAGE4_DISCORDANCE" python3 "$SRC/stage4_discordance.py" --config "$CONFIG"
run_stage "STAGE5_OUTCOMES" python3 "$SRC/stage5_outcomes.py" --config "$CONFIG"
run_stage "STAGE6_GENETICS" python3 "$SRC/stage6_genetics.py" --config "$CONFIG"
run_stage "STAGE8_SENSITIVITY" python3 "$SRC/stage8_sensitivity.py" --config "$CONFIG"
run_stage "STAGE7_INTEGRATE" python3 "$SRC/stage7_integrate.py" --config "$CONFIG"

echo
echo "===================================================="
if [ "$FAILED" -eq 0 ]; then
  echo "PIPELINE STATUS: SUCCESS"
else
  echo "PIPELINE STATUS: PARTIAL/FAILED - review stage return codes above"
fi
echo "===================================================="
exit "$FAILED"
