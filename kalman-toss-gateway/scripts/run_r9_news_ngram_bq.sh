#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
OUT="${R9_NGRAM_OUT:-/opt/kalman/state/r9_news_ngram}"
PROJECT="${R9_BQ_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-}}"

mkdir -p "$OUT"

echo "===== R9 NGRAM BIGQUERY READINESS ====="
echo "research_only=true"
echo "production_changed=false"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PY" "$APP_ROOT/research/r9_news_ngram_bq.py"   --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}"   --output-dir "$OUT"

GEN_RC=$?
echo "generator_rc=$GEN_RC"

if [ "$GEN_RC" -ne 0 ]; then
  return "$GEN_RC" 2>/dev/null || exit "$GEN_RC"
fi

if ! command -v bq >/dev/null 2>&1; then
  echo "[BLOCKED] bq CLI is not installed on this host."
  echo "next_action=RUN_BIGQUERY_FROM_COLAB_OR_INSTALL_GCLOUD_CLI"
  return 4 2>/dev/null || exit 4
fi

if [ -z "$PROJECT" ]; then
  echo "[BLOCKED] set R9_BQ_PROJECT_ID to a Google Cloud project used for BigQuery jobs."
  return 5 2>/dev/null || exit 5
fi

SQL="$OUT/r9_ngram_historical.sql"

echo
echo "===== BIGQUERY DRY RUN ====="
bq query   --project_id="$PROJECT"   --location=US   --use_legacy_sql=false   --dry_run   --format=prettyjson   < "$SQL"   | tee "$OUT/dry_run.json"

DRY_RC=${PIPESTATUS[0]}
echo "dry_run_rc=$DRY_RC"

if [ "$DRY_RC" -ne 0 ]; then
  return "$DRY_RC" 2>/dev/null || exit "$DRY_RC"
fi

if [ "${R9_NGRAM_EXECUTE:-NO}" != "YES" ]; then
  echo
  echo "[SAFE STOP] dry-run only."
  echo "Review bytes processed before setting R9_NGRAM_EXECUTE=YES."
  return 0 2>/dev/null || exit 0
fi

echo
echo "===== BIGQUERY EXECUTE ====="
bq query   --project_id="$PROJECT"   --location=US   --use_legacy_sql=false   --format=csv   --max_rows=200000   < "$SQL"   > "$OUT/result.csv"

QUERY_RC=$?
echo "query_rc=$QUERY_RC"

if [ "$QUERY_RC" -ne 0 ]; then
  return "$QUERY_RC" 2>/dev/null || exit "$QUERY_RC"
fi

echo
echo "===== SUMMARIZE ====="
"$PY" "$APP_ROOT/research/r9_news_ngram_bq.py"   --events "${R9_SEC_EVENTS:-/opt/kalman/state/r8_sec/events.json}"   --output-dir "$OUT"   --summarize-csv "$OUT/result.csv"

echo
echo "MANIFEST=$OUT/manifest.json"
