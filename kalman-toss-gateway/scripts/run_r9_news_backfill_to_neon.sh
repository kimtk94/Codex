#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
BQ_PROJECT="${R9_BQ_PROJECT:-}"
SQL="$STATE/r9_ngram_historical.sql"
REG="$STATE/alias_registry.csv"
CSV="$STATE/r9_ngram_historical.csv"
MANIFEST="$STATE/manifest.json"

mkdir -p "$STATE"

echo "===== R9 NEWS: BUILD 93-SYMBOL REGISTRY ====="
"$PY" "$ROOT/research/r9_news_ngram_bq.py" --output-dir "$STATE"

"$PY" - "$REG" <<'PY'
import sys
import pandas as pd
p=sys.argv[1]
x=pd.read_csv(p)
supported=int(x["status"].eq("SUPPORTED").sum())
needs=int(x["status"].ne("SUPPORTED").sum())
print(f"universe={len(x)} supported={supported} needs_override={needs}")
if len(x) != 93 or supported != 93 or needs != 0:
    raise SystemExit("R9 alias contract is not 93/93")
PY

echo
echo "===== R9 NEWS: BIGQUERY DRY RUN ====="
if ! command -v bq >/dev/null 2>&1; then
  echo "ERROR: bq CLI not found" >&2
  exit 20
fi
if [[ -z "$BQ_PROJECT" ]]; then
  echo "ERROR: set R9_BQ_PROJECT to the GCP billing project" >&2
  exit 21
fi

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1 || true)"
echo "gcloud_account=${ACTIVE_ACCOUNT:-NONE}"
echo "billing_project=$BQ_PROJECT"

if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  echo "ERROR: no active gcloud account." >&2
  echo "Run: gcloud auth login --no-launch-browser" >&2
  echo "Then rerun this script." >&2
  exit 22
fi

bq --project_id="$BQ_PROJECT" query \
  --use_legacy_sql=false \
  --dry_run \
  < "$SQL"

if [[ "${R9_NGRAM_EXECUTE:-NO}" != "YES" ]]; then
  echo
  echo "STOP_AFTER_DRY_RUN: set R9_NGRAM_EXECUTE=YES for the historical extraction."
  exit 0
fi

echo
echo "===== R9 NEWS: HISTORICAL EXTRACTION ====="
TMP="$CSV.tmp"
rm -f "$TMP"
bq --project_id="$BQ_PROJECT" query \
  --use_legacy_sql=false \
  --quiet \
  --format=csv \
  --max_rows=1000000 \
  < "$SQL" > "$TMP"
mv "$TMP" "$CSV"

echo
echo "===== R9 NEWS: READINESS ====="
"$PY" "$ROOT/research/r9_news_ngram_bq.py" \
  --output-dir "$STATE" \
  --summarize-csv "$CSV"

echo
echo "===== R9 NEWS: NEON VALIDATION ====="
"$PY" "$ROOT/research/r9_news_neon_store.py" \
  --registry "$REG" \
  --mentions-csv "$CSV" \
  --manifest "$MANIFEST" \
  --dry-run

if [[ "${R9_NEON_WRITE:-NO}" != "YES" ]]; then
  echo
  echo "STOP_BEFORE_NEON_WRITE: set R9_NEON_WRITE=YES after the research schema exists."
  exit 0
fi

echo
echo "===== R9 NEWS: NEON MIRROR ====="
sudo env \
  KALMAN_ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}" \
  KALMAN_R9_NEWS_NEON_ENABLED=true \
  KALMAN_R9_NEWS_NEON_CONFIRM=CONFIRM_R9_NEWS_NEON_STORE \
  "$PY" "$ROOT/research/r9_news_neon_store.py" \
    --registry "$REG" \
    --mentions-csv "$CSV" \
    --manifest "$MANIFEST"

echo
echo "R9_NEWS_BACKFILL_TO_NEON=PASS"
