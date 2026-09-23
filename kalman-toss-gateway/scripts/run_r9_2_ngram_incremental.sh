#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
BQ_PROJECT="${R9_BQ_PROJECT:-}"
BQ_LOCATION="${R9_BQ_LOCATION:-US}"
MAX_BYTES="${R9_DAILY_BQ_MAX_BYTES_BILLED:-4294967296}"

REG="${R9_ALIAS_REGISTRY:-$STATE/alias_registry.csv}"
HIST="${R9_HISTORICAL_MENTIONS:-$STATE/r9_ngram_historical.csv}"
SHADOW_HIST="${R9_SHADOW_HISTORY:-$STATE/r9_ngram_shadow_history.csv}"
SNAPSHOT="${R9_SHADOW_FEATURE_SNAPSHOT:-$STATE/r9_shadow_feature_snapshot.csv}"
SOURCE_STATE="${R9_SHADOW_SOURCE_STATE:-$STATE/r9_shadow_source_state.json}"
SQL="$STATE/r9_2_ngram_incremental.sql"
CSV="$STATE/r9_2_ngram_incremental.csv"

START_DAY="${R9_NGRAM_START_DAY:-$(date -u -d 'yesterday' +%F)}"
if [[ -n "${R9_NGRAM_END_DAY_EXCLUSIVE:-}" ]]; then
  END_DAY="${R9_NGRAM_END_DAY_EXCLUSIVE}"
else
  END_DAY="$(date -u -d "$START_DAY + 1 day" +%F)"
fi

mkdir -p "$STATE"

run_py() {
  sudo env \
    PYTHONPATH="$ROOT/research:$ROOT" \
    "$PY" "$@"
}

if ! sudo test -x "$PY"; then
  echo "ERROR: protected Python missing/not executable as root: $PY" >&2
  exit 20
fi
if [[ -z "$BQ_PROJECT" ]]; then
  echo "ERROR: set R9_BQ_PROJECT" >&2
  exit 21
fi
if [[ ! -s "$REG" || ! -s "$HIST" ]]; then
  echo "ERROR: R9 registry/history missing" >&2
  exit 22
fi
if ! command -v bq >/dev/null 2>&1; then
  echo "ERROR: bq CLI not found" >&2
  exit 23
fi

echo "===== R9.2 NGRAM INCREMENTAL SOURCE ====="
echo "start_day=$START_DAY"
echo "end_day_exclusive=$END_DAY"
echo "billing_project=$BQ_PROJECT"
echo "maximum_bytes_billed=$MAX_BYTES"
echo "production_changed=false"
echo "live_execution=false"

run_py "$ROOT/research/r9_2_ngram_daily.py" build-sql \
  --registry "$REG" \
  --start-day "$START_DAY" \
  --end-day-exclusive "$END_DAY" \
  --output "$SQL"

echo
echo "===== BIGQUERY DRY RUN ====="
bq --project_id="$BQ_PROJECT" --location="$BQ_LOCATION" query \
  --use_legacy_sql=false \
  --dry_run \
  < "$SQL"

if [[ "${R9_NGRAM_INCREMENTAL_EXECUTE:-NO}" != "YES" ]]; then
  echo
  echo "STOP_AFTER_DRY_RUN: set R9_NGRAM_INCREMENTAL_EXECUTE=YES to fetch this bounded range."
  exit 0
fi

echo
echo "===== BIGQUERY BOUNDED EXTRACTION ====="
TMP="$CSV.tmp"
ERR="$STATE/r9_2_ngram_incremental.err"
rm -f "$TMP" "$ERR"

set +e
bq --project_id="$BQ_PROJECT" --location="$BQ_LOCATION" query \
  --use_legacy_sql=false \
  --quiet \
  --maximum_bytes_billed="$MAX_BYTES" \
  --format=csv \
  --max_rows=100000 \
  < "$SQL" > "$TMP" 2> "$ERR"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  STATUS="FAILED"
  if grep -Eqi 'quota|billing|maximum.*bytes|bytes billed' "$ERR"; then
    STATUS="BLOCKED_QUOTA"
  fi
  echo "ERROR: bounded GDELT query failed status=$STATUS rc=$RC" >&2
  cat "$ERR" >&2 || true
  run_py "$ROOT/research/r9_2_ngram_daily.py" mark-state \
    --state "$SOURCE_STATE" \
    --status "$STATUS" \
    --end-day-exclusive "$END_DAY" \
    --message "$(tr '\n' ' ' < "$ERR" | head -c 1000)"
  exit "$RC"
fi

mv "$TMP" "$CSV"

echo
echo "===== VALIDATE / CALENDAR-COMPLETE / SNAPSHOT ====="
NEON_ARGS=()
if [[ "${R9_2_NEON_WRITE:-NO}" == "YES" ]]; then
  NEON_ARGS+=(--write-neon)
fi

sudo env \
  PYTHONPATH="$ROOT/research:$ROOT" \
  KALMAN_ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}" \
  KALMAN_R9_2_DAILY_NEON_ENABLED="${KALMAN_R9_2_DAILY_NEON_ENABLED:-false}" \
  KALMAN_R9_2_DAILY_NEON_CONFIRM="${KALMAN_R9_2_DAILY_NEON_CONFIRM:-}" \
  "$PY" "$ROOT/research/r9_2_ngram_daily.py" finalize \
    --registry "$REG" \
    --csv "$CSV" \
    --historical "$HIST" \
    --shadow-history "$SHADOW_HIST" \
    --snapshot "$SNAPSHOT" \
    --state "$SOURCE_STATE" \
    --start-day "$START_DAY" \
    --end-day-exclusive "$END_DAY" \
    "${NEON_ARGS[@]}"

echo
echo "R9_2_NGRAM_INCREMENTAL=PASS"
echo "No production trading state changed."
