#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

PROJECT="/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging"
RESULTS="/srv/is-analysis/results/multi_organ_aging"
REMOTE="gdrive:IS_Analysis_V3/MULTI_ORGAN_AGING"

echo "===================================================="
echo "MULTI-ORGAN AGING -> IS_Analysis_V3 DRIVE MIRROR"
echo "===================================================="

if ! command -v rclone >/dev/null 2>&1; then
  echo "[ERROR] rclone not found"
  exit 2
fi

if ! rclone listremotes 2>/dev/null | grep -qx "gdrive:"; then
  echo "[ERROR] rclone remote gdrive: not configured"
  exit 3
fi

mkdir -p "$RESULTS"

PROV="$RESULTS/GIT_PROVENANCE.txt"
{
  echo "generated_at=$(date -Iseconds)"
  echo "project=$PROJECT"
  echo "repo=$(git -C "$PROJECT" rev-parse --show-toplevel 2>/dev/null || echo unknown)"
  echo "branch=$(git -C "$PROJECT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "commit=$(git -C "$PROJECT" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "dirty=$(git -C "$PROJECT" status --porcelain 2>/dev/null | wc -l)"
} > "$PROV"

echo
echo "===== CODE ====="
rclone copy "$PROJECT" "$REMOTE/code" \
  --exclude '.git/**' \
  --exclude '__pycache__/**' \
  --exclude '*.pyc' \
  --progress
RC_CODE=$?

echo
echo "===== INPUT MANIFEST ====="
AUDIT="$RESULTS/stage0_audit"
if [ -d "$AUDIT" ]; then
  rclone copy "$AUDIT" "$REMOTE/input_manifest" \
    --include 'WAVE_FILE_MANIFEST.tsv' \
    --include 'VARIABLE_COVERAGE.tsv' \
    --include 'ORGAN_FEASIBILITY.tsv' \
    --include 'STAGE0_SUMMARY.json' \
    --exclude '*' \
    --progress
  RC_INPUT=$?
else
  echo "[WARN] Stage0 audit directory not found."
  RC_INPUT=0
fi

echo
echo "===== RESULTS ====="
rclone copy "$RESULTS" "$REMOTE/results" \
  --exclude 'models/**' \
  --exclude '*.pkl' \
  --exclude '*.joblib' \
  --progress
RC_RESULTS=$?

echo
echo "===== REPORTS ====="
rclone copy "$RESULTS" "$REMOTE/reports" \
  --include '*SUMMARY.json' \
  --include '*REPORT.md' \
  --include '*PERFORMANCE.tsv' \
  --include '*EVIDENCE_MATRIX.tsv' \
  --include 'CLUSTER_CENTROIDS.tsv' \
  --include 'CLUSTER_COUNTS.tsv' \
  --include 'GIT_PROVENANCE.txt' \
  --exclude '*' \
  --progress
RC_REPORTS=$?

echo
echo "code=$RC_CODE input=$RC_INPUT results=$RC_RESULTS reports=$RC_REPORTS"

if [ "$RC_CODE" -ne 0 ] || [ "$RC_INPUT" -ne 0 ] || [ "$RC_RESULTS" -ne 0 ] || [ "$RC_REPORTS" -ne 0 ]; then
  echo "SYNC STATUS: PARTIAL/FAILED"
  exit 1
fi

echo "SYNC STATUS: SUCCESS"
exit 0
