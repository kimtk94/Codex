#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ROOT="/srv/is-analysis"
REPO="$ROOT/IS_Analysis_V3"
BASE="$REPO/master_degree/multi_organ_aging"
CFG="$BASE/config/organ_domains.yaml"

KOGES_INPUT="${KOGES_INPUT:-$ROOT/data/metabolic_resilience/stage0_koges/public_training}"
RESULT_ROOT="${RESULT_ROOT:-$ROOT/results/multi_organ_aging}"

mkdir -p   "$RESULT_ROOT/stage0"   "$RESULT_ROOT/stage1"   "$RESULT_ROOT/stage2"   "$RESULT_ROOT/stage3"   "$RESULT_ROOT/stage4"   "$RESULT_ROOT/stage5"   "$RESULT_ROOT/stage6"   "$RESULT_ROOT/stage7"

echo "===== MULTI-ORGAN AGING PIPELINE ====="
echo "repo=$REPO"
echo "input=$KOGES_INPUT"
echo "results=$RESULT_ROOT"

python3 "$BASE/src/stage0_audit.py"   --input-dir "$KOGES_INPUT"   --config "$CFG"   --outdir "$RESULT_ROOT/stage0"
RC0=$?
echo "stage0 rc=$RC0"

python3 "$BASE/src/stage1_panel.py"   --input-dir "$KOGES_INPUT"   --config "$CFG"   --outdir "$RESULT_ROOT/stage1"
RC1=$?
echo "stage1 rc=$RC1"

RC2=99
if [ "$RC1" -eq 0 ] && [ -f "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet" ]; then
  python3 "$BASE/src/stage2_organ_age.py"     --panel "$RESULT_ROOT/stage1/STAGE1_LONG_PANEL.parquet"     --config "$CFG"     --outdir "$RESULT_ROOT/stage2"
  RC2=$?
fi
echo "stage2 rc=$RC2"

RC3=99
if [ "$RC2" -eq 0 ] && [ -f "$RESULT_ROOT/stage2/STAGE2_ORGAN_AGE_SCORES.parquet" ]; then
  python3 "$BASE/src/stage3_longitudinal.py"     --scores "$RESULT_ROOT/stage2/STAGE2_ORGAN_AGE_SCORES.parquet"     --outdir "$RESULT_ROOT/stage3"
  RC3=$?
fi
echo "stage3 rc=$RC3"

RC4=99
if [ "$RC3" -eq 0 ] && [ -f "$RESULT_ROOT/stage3/STAGE3_SUBJECT_TRAJECTORIES.parquet" ]; then
  python3 "$BASE/src/stage4_discordance.py"     --trajectories "$RESULT_ROOT/stage3/STAGE3_SUBJECT_TRAJECTORIES.parquet"     --config "$CFG"     --outdir "$RESULT_ROOT/stage4"
  RC4=$?
fi
echo "stage4 rc=$RC4"

python3 "$BASE/src/stage7_report.py"   --result-root "$RESULT_ROOT"   --out "$RESULT_ROOT/stage7/MULTI_ORGAN_AGING_STATUS.md"
RC7=$?
echo "stage7 rc=$RC7"

printf "FINAL stage0=%s stage1=%s stage2=%s stage3=%s stage4=%s stage7=%s\n"   "$RC0" "$RC1" "$RC2" "$RC3" "$RC4" "$RC7"

exit 0
