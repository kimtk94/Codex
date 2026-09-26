#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ROOT="/srv/is-analysis"
REPO="$ROOT/IS_Analysis_V3"
BASE="$REPO/master_degree/multi_organ_aging"
CFG="$BASE/config/organ_domains.yaml"
RESULT_ROOT="${RESULT_ROOT:-$ROOT/results/multi_organ_aging}"
RUN_SENSITIVITY="${RUN_SENSITIVITY:-0}"
VARIABLE_MAP="${VARIABLE_MAP:-}"

if [ -z "${KOGES_INPUT:-}" ]; then
  CANDIDATES=(
    "$ROOT/data/metabolic_resilience/stage0_koges/public_training"
    "$ROOT/data/metabolic_resilience/stage0/public_training"
    "$ROOT/data/ckd/stage4_koges/public_training"
    "$ROOT/results/metabolic_resilience/stage0_koges/public_training"
  )
  for CANDIDATE in "${CANDIDATES[@]}"; do
    if [ -d "$CANDIDATE" ]; then
      KOGES_INPUT="$CANDIDATE"
      break
    fi
  done
fi

KOGES_INPUT="${KOGES_INPUT:-$ROOT/data/ckd/stage4_koges/public_training}"

if [ -z "$VARIABLE_MAP" ] && [ -f "$BASE/config/variable_map_frozen.tsv" ]; then
  VARIABLE_MAP="$BASE/config/variable_map_frozen.tsv"
fi

STAGES=(stage0 stage0b stage1 stage1b stage2 stage2b stage3 stage4 stage4b stage5 stage6 stage7)
for STAGE in "${STAGES[@]}"; do
  mkdir -p "$RESULT_ROOT/$STAGE"
done

echo "===== MULTI-ORGAN AGING PIPELINE ====="
echo "repo=$REPO"
echo "input=$KOGES_INPUT"
echo "results=$RESULT_ROOT"
echo "run_sensitivity=$RUN_SENSITIVITY"
echo "variable_map=${VARIABLE_MAP:-AUTO_DISCOVERY}"

python3 "$BASE/src/stage0_audit.py" --input-dir "$KOGES_INPUT" --config "$CFG" --outdir "$RESULT_ROOT/stage0"
RC0=$?
echo "stage0 rc=$RC0"

RC0B=99
if [ "$RC0" -eq 0 ] && [ -f "$RESULT_ROOT/stage0/STAGE0_VARIABLE_CANDIDATES.tsv" ]; then
  python3 "$BASE/src/stage0b_draft_map.py" --candidates "$RESULT_ROOT/stage0/STAGE0_VARIABLE_CANDIDATES.tsv" --out "$RESULT_ROOT/stage0b/STAGE0B_VARIABLE_MAP_DRAFT.tsv"
  RC0B=$?
fi
echo "stage0b rc=$RC0B"

if [ -n "$VARIABLE_MAP" ] && [ -f "$VARIABLE_MAP" ]; then
  python3 "$BASE/src/stage1_panel.py" --input-dir "$KOGES_INPUT" --config "$CFG" --mapping "$VARIABLE_MAP" --outdir "$RESULT_ROOT/stage1"
else
  python3 "$BASE/src/stage1_panel.py" --input-dir "$KOGES_INPUT" --config "$CFG" --outdir "$RESULT_ROOT/stage1"
fi
RC1=$?
echo "stage1 rc=$RC1"

RC1B=99
if [ "$RC1" -eq 0 ] && [ -f "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" ]; then
  python3 "$BASE/src/stage1b_eligibility.py" --panel "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" --config "$CFG" --outdir "$RESULT_ROOT/stage1b"
  RC1B=$?
fi
echo "stage1b rc=$RC1B"

RC2=99
if [ "$RC1" -eq 0 ] && [ -f "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" ]; then
  python3 "$BASE/src/stage2_organ_age.py" --panel "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" --config "$CFG" --outdir "$RESULT_ROOT/stage2"
  RC2=$?
fi
echo "stage2 rc=$RC2"

RC2B=0
if [ "$RUN_SENSITIVITY" = "1" ] && [ "$RC1" -eq 0 ] && [ -f "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" ]; then
  python3 "$BASE/src/stage2b_sensitivity.py" --panel "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" --config "$CFG" --outdir "$RESULT_ROOT/stage2b"
  RC2B=$?
fi
echo "stage2b rc=$RC2B"

RC3=99
if [ "$RC2" -eq 0 ] && [ -f "$RESULT_ROOT/stage2/STAGE2_ORGAN_AGE_SCORES.parquet" ]; then
  python3 "$BASE/src/stage3_longitudinal.py" --scores "$RESULT_ROOT/stage2/STAGE2_ORGAN_AGE_SCORES.parquet" --outdir "$RESULT_ROOT/stage3"
  RC3=$?
fi
echo "stage3 rc=$RC3"

RC4=99
if [ "$RC3" -eq 0 ] && [ -f "$RESULT_ROOT/stage3/STAGE3_SUBJECT_TRAJECTORIES.parquet" ]; then
  python3 "$BASE/src/stage4_discordance.py" --trajectories "$RESULT_ROOT/stage3/STAGE3_SUBJECT_TRAJECTORIES.parquet" --config "$CFG" --outdir "$RESULT_ROOT/stage4"
  RC4=$?
fi
echo "stage4 rc=$RC4"

RC4B=99
if [ "$RC4" -eq 0 ] && [ -f "$RESULT_ROOT/stage4/STAGE4_DISCORDANCE_PHENOTYPES.parquet" ]; then
  python3 "$BASE/src/stage4b_qc.py" --phenotypes "$RESULT_ROOT/stage4/STAGE4_DISCORDANCE_PHENOTYPES.parquet" --outdir "$RESULT_ROOT/stage4b"
  RC4B=$?
fi
echo "stage4b rc=$RC4B"

python3 "$BASE/src/stage7_report.py" --result-root "$RESULT_ROOT" --out "$RESULT_ROOT/stage7/MULTI_ORGAN_AGING_STATUS.md"
RC7=$?
echo "stage7 rc=$RC7"

printf "FINAL stage0=%s stage0b=%s stage1=%s stage1b=%s stage2=%s stage2b=%s stage3=%s stage4=%s stage4b=%s stage7=%s\n" "$RC0" "$RC0B" "$RC1" "$RC1B" "$RC2" "$RC2B" "$RC3" "$RC4" "$RC4B" "$RC7"

exit 0
