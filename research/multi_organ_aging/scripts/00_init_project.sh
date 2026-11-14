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

mkdir -p "$PROJECT/config" "$PROJECT/scripts" "$PROJECT/src"
mkdir -p "$DATA/public_training" "$DATA/approved" "$DATA/controlled" "$DATA/genetics"

for D in \
  stage0_audit \
  stage1_longitudinal \
  stage2_clocks \
  stage3_pace \
  stage4_discordance \
  stage5_outcomes \
  stage6_genetics \
  stage7_integrated \
  stage8_sensitivity \
  models
do
  mkdir -p "$RESULTS/$D"
done

echo "===== MULTI-ORGAN AGING INIT ====="
echo "PROJECT=$PROJECT"
echo "DATA=$DATA"
echo "RESULTS=$RESULTS"

SHARED="$DATA/public_training/shared_source"

if [ -L "$SHARED" ]; then
  rm -f "$SHARED"
fi

for SRC in \
  "/srv/is-analysis/data/ckd/stage4_koges/public_training" \
  "/srv/is-analysis/data/metabolic_resilience/stage0_koges/public_training" \
  "/srv/is-analysis/data/metabolic_resilience/public_training"
do
  if [ -d "$SRC" ]; then
    echo "[FOUND SHARED KOGES] $SRC"
    if [ ! -e "$SHARED" ]; then
      ln -s "$SRC" "$SHARED" 2>/dev/null
      echo "[LINKED] $SHARED -> $SRC"
    fi
    break
  fi
done

if [ ! -e "$SHARED" ]; then
  echo "[WARN] shared KoGES public-training source not found."
  echo "[WARN] Place public files under $DATA/public_training or set --input-dir manually."
fi

echo "===== DONE ====="
