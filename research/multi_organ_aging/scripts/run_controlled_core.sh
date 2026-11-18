#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG="${1:-$BASE/config/multi_organ_aging.json}"
INPUT_DIR="${2:-/srv/is-analysis/data/multi_organ_aging/controlled}"
RESULTS="${3:-/srv/is-analysis/results/multi_organ_aging/controlled_analysis}"
PYTHON_BIN="${PYTHON_BIN:-/srv/is-analysis/.venvs/multi_organ_aging/bin/python}"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

mkdir -p "$RESULTS" "$RESULTS/models"

echo "============================================================"
echo "MULTI-ORGAN AGING — CONTROLLED CORE PIPELINE"
echo "============================================================"
echo "CONFIG=$CONFIG"
echo "INPUT_DIR=$INPUT_DIR"
echo "RESULTS=$RESULTS"
echo "PYTHON_BIN=$PYTHON_BIN"

RC0C=99
RC1=99
RC2=99
RC2B=99
RC3=99
RC4=99
RC8=99
GO="HOLD"

echo
echo "===== STAGE 0C — READINESS ====="

"$PYTHON_BIN"   "$BASE/src/stage0c_controlled_readiness.py"   --config "$CONFIG"   --input-dir "$INPUT_DIR"   --out-dir "$RESULTS"

RC0C=$?

SUMMARY="$RESULTS/stage0c_controlled_readiness/CONTROLLED_READINESS_SUMMARY.json"

if [ "$RC0C" -eq 0 ] && [ -f "$SUMMARY" ]; then
  GO=$(
    "$PYTHON_BIN" - "$SUMMARY" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    x = json.loads(p.read_text(encoding="utf-8"))
    print(x.get("go_no_go", "HOLD"))
except Exception:
    print("HOLD")
PY
  )
fi

echo "STAGE0C_RC=$RC0C"
echo "GO_NO_GO=$GO"

if [ -f "$SUMMARY" ]; then
  cat "$SUMMARY"
fi

if [ "$RC0C" -eq 0 ] && [ "$GO" = "GO" ]; then

  echo
  echo "===== STAGE 1 — CONTROLLED LONGITUDINAL PANEL ====="

  "$PYTHON_BIN"     "$BASE/src/stage1_build_longitudinal.py"     --config "$CONFIG"     --input-dir "$INPUT_DIR"     --out-dir "$RESULTS"

  RC1=$?
  echo "STAGE1_RC=$RC1"

  if [ "$RC1" -eq 0 ]; then

    echo
    echo "===== STAGE 2 — CONTROLLED ORGAN CLOCKS ====="

    "$PYTHON_BIN"       "$BASE/src/stage2_train_organ_clocks.py"       --config "$CONFIG"       --out-dir "$RESULTS"       --model-dir "$RESULTS/models"

    RC2=$?
    echo "STAGE2_RC=$RC2"

  fi

  if [ "$RC2" -eq 0 ]; then

    echo
    echo "===== STAGE 2B — SUBJECT-LEVEL CROSSFIT ====="

    "$PYTHON_BIN"       "$BASE/src/stage2b_crossfit_longitudinal.py"       --config "$CONFIG"       --out-dir "$RESULTS"

    RC2B=$?
    echo "STAGE2B_RC=$RC2B"

  fi

  CROSS="$RESULTS/stage2b_crossfit/ORGAN_AGE_SCORES_LONG_CROSSFIT.tsv.gz"

  if [ "$RC2B" -eq 0 ] && [ -f "$CROSS" ]; then

    echo
    echo "===== STAGE 3 — CONTROLLED AGING PACE ====="

    "$PYTHON_BIN"       "$BASE/src/stage3_estimate_pace.py"       --config "$CONFIG"       --scores "$CROSS"       --out-dir "$RESULTS"

    RC3=$?
    echo "STAGE3_RC=$RC3"

  fi

  if [ "$RC3" -eq 0 ]; then

    echo
    echo "===== STAGE 4 — CONTROLLED MULTI-ORGAN DISCORDANCE ====="

    "$PYTHON_BIN"       "$BASE/src/stage4_discordance.py"       --config "$CONFIG"       --out-dir "$RESULTS"

    RC4=$?
    echo "STAGE4_RC=$RC4"

    echo
    echo "===== STAGE 8 — DESCRIPTIVE SENSITIVITY ====="

    "$PYTHON_BIN"       "$BASE/src/stage8_sensitivity.py"       --config "$CONFIG"       --out-dir "$RESULTS"

    RC8=$?
    echo "STAGE8_RC=$RC8"

  fi

else
  echo
  echo "CONTROLLED CORE PIPELINE NOT STARTED"
  echo "Reason: readiness is not GO or Stage 0C failed."
  echo "No public-prototype results were modified."
fi

echo
echo "============================================================"
echo "CONTROLLED CORE STATUS"
echo "============================================================"
echo "STAGE0C=$RC0C"
echo "GO_NO_GO=$GO"
echo "STAGE1=$RC1"
echo "STAGE2=$RC2"
echo "STAGE2B=$RC2B"
echo "STAGE3=$RC3"
echo "STAGE4=$RC4"
echo "STAGE8=$RC8"
echo "RESULTS=$RESULTS"

if [ -f "$RESULTS/stage2_clocks/STAGE2_SUMMARY.json" ]; then
  echo
  echo "===== TRAINED ORGANS ====="
  cat "$RESULTS/stage2_clocks/STAGE2_SUMMARY.json"
fi

if [ -f "$RESULTS/stage3_pace/STAGE3_SUMMARY.json" ]; then
  echo
  echo "===== PACE SUMMARY ====="
  cat "$RESULTS/stage3_pace/STAGE3_SUMMARY.json"
fi

if [ -f "$RESULTS/stage4_discordance/STAGE4_SUMMARY.json" ]; then
  echo
  echo "===== DISCORDANCE SUMMARY ====="
  cat "$RESULTS/stage4_discordance/STAGE4_SUMMARY.json"
fi

echo
echo "NOTE: controlled outcome models are intentionally NOT run by this script."
echo "Outcome definitions must be frozen after core phenotype QC."
echo
echo "SHELL_STILL_ALIVE"
