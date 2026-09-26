#!/usr/bin/env bash
set +e
set +u
set +o pipefail 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT="/srv/is-analysis"
RESULTS="$ROOT/results/multi_organ_aging"
REMOTE="gdrive:MASTER_DEGREE/MULTI_ORGAN_AGING"

echo "===================================================="
echo "MULTI-ORGAN AGING -> GOOGLE DRIVE SYNC"
echo "===================================================="

if ! command -v rclone >/dev/null 2>&1; then
  echo "[ERROR] rclone not found"
  exit 2
fi

if ! rclone listremotes 2>/dev/null | grep -qx "gdrive:"; then
  echo "[ERROR] rclone remote gdrive: not configured"
  exit 3
fi

PROV="$BASE/GIT_PROVENANCE.txt"
{
  echo "generated_at=$(date -Iseconds)"
  echo "repo=$(git -C "$BASE" rev-parse --show-toplevel 2>/dev/null)"
  echo "branch=$(git -C "$BASE" rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "commit=$(git -C "$BASE" rev-parse HEAD 2>/dev/null)"
  echo "dirty=$(git -C "$BASE" status --porcelain 2>/dev/null | wc -l)"
} > "$PROV"

echo
echo "===== 00_MASTER ====="
rclone copy "$BASE" "$REMOTE/00_MASTER"   --include "MULTI_ORGAN_AGING_MASTER.md"   --include "README.md"   --include "GIT_PROVENANCE.txt"   --progress
RC_MASTER=$?

echo
echo "===== 02_CODE ====="
rclone copy "$BASE" "$REMOTE/02_CODE/git_snapshot"   --exclude "__pycache__/**"   --exclude "*.pyc"   --exclude ".DS_Store"   --progress
RC_CODE=$?

echo
echo "===== 03_RESULTS ====="
if [ -d "$RESULTS" ]; then
  rclone copy "$RESULTS" "$REMOTE/03_RESULTS"     --exclude "models/**"     --exclude "*.pkl"     --progress
  RC_RESULTS=$?
else
  echo "[WARN] results directory does not exist yet: $RESULTS"
  RC_RESULTS=0
fi

echo
echo "===== 04_REPORTS ====="
if [ -d "$RESULTS" ]; then
  rclone copy "$RESULTS" "$REMOTE/04_REPORTS"     --include "*SUMMARY.json"     --include "*REPORT.md"     --include "*PERFORMANCE.tsv"     --include "*EVIDENCE_MATRIX.tsv"     --include "CLUSTER_CENTROIDS.tsv"     --include "CLUSTER_COUNTS.tsv"     --exclude "*"     --progress
  RC_REPORTS=$?
else
  RC_REPORTS=0
fi

echo
echo "===== 01_INPUT MANIFEST ONLY ====="
AUDIT="$RESULTS/stage0_audit"
if [ -d "$AUDIT" ]; then
  rclone copy "$AUDIT" "$REMOTE/01_INPUT"     --include "WAVE_FILE_MANIFEST.tsv"     --include "VARIABLE_COVERAGE.tsv"     --include "ORGAN_FEASIBILITY.tsv"     --exclude "*"     --progress
  RC_INPUT=$?
else
  RC_INPUT=0
fi

echo
echo "master=$RC_MASTER code=$RC_CODE results=$RC_RESULTS reports=$RC_REPORTS input=$RC_INPUT"
if [ "$RC_MASTER" -ne 0 ] || [ "$RC_CODE" -ne 0 ] || [ "$RC_RESULTS" -ne 0 ] || [ "$RC_REPORTS" -ne 0 ] || [ "$RC_INPUT" -ne 0 ]; then
  echo "SYNC STATUS: PARTIAL/FAILED"
  exit 1
fi

echo "SYNC STATUS: SUCCESS"
exit 0
