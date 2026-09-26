#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

CODE_ROOT="/srv/is-analysis/IS_Analysis_V3"
PROJECT="$CODE_ROOT/research/multi_organ_aging"
DATA_ROOT="/srv/is-analysis/data"
RESULT_ROOT="/srv/is-analysis/results"
DATA="$DATA_ROOT/multi_organ_aging"
RESULTS="$RESULT_ROOT/multi_organ_aging"

mkdir -p "$PROJECT/config" "$PROJECT/scripts"
mkdir -p "$DATA/public_training" "$DATA/approved" "$DATA/genetics"
mkdir -p "$RESULTS/stage0_audit" "$RESULTS/stage1_panel" "$RESULTS/stage2_organ_age"
mkdir -p "$RESULTS/stage3_pace" "$RESULTS/stage4_patterns" "$RESULTS/stage5_outcomes"
mkdir -p "$RESULTS/stage6_association" "$RESULTS/stage7_genetics" "$RESULTS/stage8_summary"

echo "===== MULTI-ORGAN AGING INIT ====="
echo "PROJECT=$PROJECT"
echo "DATA=$DATA"
echo "RESULTS=$RESULTS"

for SRC in   "/srv/is-analysis/data/metabolic_resilience/stage0_koges/public_training"   "/srv/is-analysis/data/ckd/stage4_koges/public_training"
do
  if [ -d "$SRC" ]; then
    echo "[FOUND SHARED KOGES] $SRC"
    if [ ! -e "$DATA/public_training/shared_source" ]; then
      ln -s "$SRC" "$DATA/public_training/shared_source" 2>/dev/null
    fi
    break
  fi
done

echo "===== DONE ====="
