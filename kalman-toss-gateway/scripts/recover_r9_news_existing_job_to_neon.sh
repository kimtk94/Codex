#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${R9_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE="${R9_NEWS_STATE_DIR:-${HOME}/.local/state/kalman/r9_news_ngram}"
BQ_PROJECT="${R9_BQ_PROJECT:-btc-gdelt-20260817-76la2}"
BQ_LOCATION="${R9_BQ_LOCATION:-US}"
JOB_ID="${R9_EXISTING_JOB_ID:-}"
START_DAY="${R9_START_DAY:-20240801}"
END_DAY="${R9_END_DAY:-20260902}"

FULL="$STATE/r9_ngram_historical_38m_existing.csv"
CSV="$STATE/r9_ngram_historical.csv"
REG="$STATE/alias_registry.csv"
MANIFEST="$STATE/manifest.json"
JOB_META="$STATE/existing_job.json"

if [[ -z "$JOB_ID" ]]; then
  echo "ERROR: set R9_EXISTING_JOB_ID to the completed BigQuery job id" >&2
  exit 20
fi

mkdir -p "$STATE"

run_py() {
  sudo env \
    PYTHONPATH="$ROOT" \
    "$PY" "$@"
}

echo "===== R9 RECOVERY: JOB METADATA (NO NEW QUERY) ====="
bq \
  --project_id="$BQ_PROJECT" \
  --location="$BQ_LOCATION" \
  --format=prettyjson \
  show \
  --job=true \
  "$JOB_ID" > "$JOB_META"

TABLE_REF="$(
python3 - "$JOB_META" <<'PY'
import json, sys
p=sys.argv[1]
obj=json.load(open(p, encoding="utf-8"))
if obj.get("status", {}).get("state") != "DONE":
    raise SystemExit("existing job is not DONE")
err=obj.get("status", {}).get("errorResult")
if err:
    raise SystemExit(f"existing job failed: {err}")
q=obj.get("statistics", {}).get("query", {})
dest=obj.get("configuration", {}).get("query", {}).get("destinationTable") or q.get("destinationTable")
if not dest:
    raise SystemExit("destinationTable missing from existing job")
project=dest.get("projectId")
dataset=dest.get("datasetId")
table=dest.get("tableId")
if not all((project,dataset,table)):
    raise SystemExit(f"incomplete destinationTable: {dest}")
processed=int(q.get("totalBytesProcessed") or obj.get("statistics", {}).get("totalBytesProcessed") or 0)
billed=int(q.get("totalBytesBilled") or 0)
print(f"{project}:{dataset}.{table}")
print(f"processed_bytes={processed}", file=sys.stderr)
print(f"billed_bytes={billed}", file=sys.stderr)
PY
)"

echo "destination_table=$TABLE_REF"

echo
echo "===== R9 RECOVERY: DOWNLOAD EXISTING RESULT (NO NEW QUERY) ====="
TMP="$FULL.tmp"
rm -f "$TMP"
bq \
  --project_id="$BQ_PROJECT" \
  --format=csv \
  head \
  --max_rows=100000 \
  "$TABLE_REF" > "$TMP"

python3 - "$TMP" <<'PY'
import csv, sys
p=sys.argv[1]
with open(p, newline="", encoding="utf-8-sig") as f:
    r=csv.DictReader(f)
    required={"symbol","day_utc","mention_count"}
    if not required.issubset(r.fieldnames or []):
        raise SystemExit(f"unexpected recovered columns: {r.fieldnames}")
    n=sum(1 for _ in r)
if n <= 0:
    raise SystemExit("recovered result is empty")
print(f"recovered_rows={n}")
PY
mv "$TMP" "$FULL"

echo
echo "===== R9 RECOVERY: LOCAL 25-MONTH FILTER ====="
TMP="$CSV.tmp"
rm -f "$TMP"
python3 - "$FULL" "$TMP" "$START_DAY" "$END_DAY" <<'PY'
import csv, sys
src,dst,start_s,end_s=sys.argv[1:5]
start=int(start_s); end=int(end_s)
kept=0
symbols=set()
lo=None; hi=None
with open(src, newline="", encoding="utf-8-sig") as fi, \
     open(dst, "w", newline="", encoding="utf-8") as fo:
    reader=csv.DictReader(fi)
    required={"symbol","day_utc","mention_count"}
    if not required.issubset(reader.fieldnames or []):
        raise SystemExit(f"unexpected columns: {reader.fieldnames}")
    writer=csv.DictWriter(fo, fieldnames=["symbol","day_utc","mention_count"])
    writer.writeheader()
    for row in reader:
        day=int(row["day_utc"])
        if start <= day < end:
            writer.writerow({
                "symbol":row["symbol"],
                "day_utc":row["day_utc"],
                "mention_count":row["mention_count"],
            })
            kept += 1
            symbols.add(row["symbol"])
            lo=day if lo is None else min(lo,day)
            hi=day if hi is None else max(hi,day)
if kept <= 0:
    raise SystemExit("25-month filtered result is empty")
print(f"filtered_rows={kept}")
print(f"symbols={len(symbols)}")
print(f"observed_day_min={lo}")
print(f"observed_day_max={hi}")
PY
mv "$TMP" "$CSV"

echo
echo "===== R9 RECOVERY: REBUILD REGISTRY + FRESH READINESS ====="
rm -f "$MANIFEST"
run_py "$ROOT/research/r9_news_ngram_bq.py" \
  --output-dir "$STATE" \
  --summarize-csv "$CSV"

echo
echo "===== R9 RECOVERY: REQUIRE FRESH READINESS PASS ====="
python3 - "$MANIFEST" <<'PY'
import json, sys
p=sys.argv[1]
m=json.load(open(p, encoding="utf-8"))
print("r9_ngram_ready =", m.get("r9_ngram_ready"))
print("symbols_with_mentions =", m.get("symbols_with_mentions"))
print("usable_span_months =", m.get("usable_span_months"))
print("gates =", m.get("gates"))
if not m.get("r9_ngram_ready"):
    raise SystemExit("STOP: fresh R9 readiness gate failed")
PY

echo
echo "===== R9 RECOVERY: NEON VALIDATION ====="
run_py "$ROOT/research/r9_news_neon_store.py" \
  --registry "$REG" \
  --mentions-csv "$CSV" \
  --manifest "$MANIFEST" \
  --dry-run

if [[ "${R9_NEON_WRITE:-NO}" != "YES" ]]; then
  echo
  echo "STOP_BEFORE_NEON_WRITE: set R9_NEON_WRITE=YES after validation."
  echo "R9_EXISTING_JOB_RECOVERY=VALIDATED"
  exit 0
fi

echo
echo "===== R9 RECOVERY: NEON MIRROR ====="
sudo env \
  KALMAN_ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}" \
  KALMAN_R9_NEWS_NEON_ENABLED=true \
  KALMAN_R9_NEWS_NEON_CONFIRM=CONFIRM_R9_NEWS_NEON_STORE \
  "$PY" "$ROOT/research/r9_news_neon_store.py" \
    --registry "$REG" \
    --mentions-csv "$CSV" \
    --manifest "$MANIFEST"

echo
echo "R9_EXISTING_JOB_RECOVERY_TO_NEON=PASS"
echo "No additional GDELT historical query was executed."
