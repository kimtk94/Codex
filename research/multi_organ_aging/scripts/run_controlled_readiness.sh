#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${1:-$BASE/config/multi_organ_aging.json}"
INPUT_DIR="${2:-/srv/is-analysis/data/multi_organ_aging/controlled}"
PYTHON_BIN="${PYTHON_BIN:-/srv/is-analysis/.venvs/multi_organ_aging/bin/python}"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

echo "===================================================="
echo "MULTI-ORGAN AGING — CONTROLLED DATA READINESS"
echo "CONFIG=$CONFIG"
echo "INPUT_DIR=$INPUT_DIR"
echo "===================================================="

"$PYTHON_BIN"   "$BASE/src/stage0c_controlled_readiness.py"   --config "$CONFIG"   --input-dir "$INPUT_DIR"

RC=$?

echo
echo "CONTROLLED_READINESS_RC=$RC"

OUT="/srv/is-analysis/results/multi_organ_aging/stage0c_controlled_readiness"

if [ -f "$OUT/CONTROLLED_READINESS_SUMMARY.json" ]; then
  echo
  echo "===== SUMMARY ====="
  cat "$OUT/CONTROLLED_READINESS_SUMMARY.json"
fi

if [ -f "$OUT/CONTROLLED_ORGAN_READINESS.tsv" ]; then
  echo
  echo "===== ORGAN READINESS ====="
  cat "$OUT/CONTROLLED_ORGAN_READINESS.tsv"
fi

echo
echo "SHELL_STILL_ALIVE"
