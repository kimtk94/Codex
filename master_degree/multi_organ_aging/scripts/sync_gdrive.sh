#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ROOT="/srv/is-analysis"
REPO="$ROOT/IS_Analysis_V3"
BASE="$REPO/master_degree/multi_organ_aging"
RESULT_ROOT="${RESULT_ROOT:-$ROOT/results/multi_organ_aging}"
REMOTE="${MOA_GDRIVE_REMOTE:-gdrive:MASTER_DEGREE/MULTI_ORGAN_AGING}"

STAMP="$(date +%Y%m%d_%H%M%S)"
MANIFEST="$RESULT_ROOT/SYNC_MANIFEST_$STAMP.txt"
mkdir -p "$RESULT_ROOT"

{
  echo "timestamp=$STAMP"
  echo "hostname=$(hostname)"
  echo "git_head=$(cd "$REPO" 2>/dev/null && git rev-parse HEAD 2>/dev/null)"
  echo "git_branch=$(cd "$REPO" 2>/dev/null && git branch --show-current 2>/dev/null)"
  echo "remote=$REMOTE"
} > "$MANIFEST"

echo "===== SYNC CODE ====="
rclone copy "$BASE" "$REMOTE/02_CODE"   --exclude "__pycache__/**"   --exclude "*.pyc"   --progress
RC_CODE=$?

echo "===== SYNC RESULTS ====="
rclone copy "$RESULT_ROOT" "$REMOTE/03_RESULTS"   --exclude "*.tmp"   --progress
RC_RESULTS=$?

echo "===== SYNC MASTER DOCS ====="
rclone copy "$BASE" "$REMOTE/00_MASTER"   --include "*.md"   --include "config/**"   --progress
RC_MASTER=$?

echo "code=$RC_CODE results=$RC_RESULTS master=$RC_MASTER"
echo "manifest=$MANIFEST"

exit 0
