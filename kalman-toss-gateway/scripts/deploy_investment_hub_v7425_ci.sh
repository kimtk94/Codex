#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
VERSION_TAG="vNext.7.4.25"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILDER="$ROOT/kalman-toss-gateway/scripts/build_investment_hub_v7425_persistent_benchmark.py"
MANIFEST="$ROOT/kalman-hub-recovery/v7.4.25/source_manifest.ndjson"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-hub-v7425-${STAMP}"
SRC="$WORK/source"
mkdir -p "$SRC"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

need vercel
need python3
need node

echo "[0/7] Authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel authenticated"

echo "[1/7] Build audited v7.4.25 source"
python3 "$BUILDER"
[ -s "$MANIFEST" ] || fail "missing generated source manifest"

python3 - "$MANIFEST" "$SRC" <<'PY'
from pathlib import Path
import base64,json,sys
manifest,out=Path(sys.argv[1]),Path(sys.argv[2])
rows=[json.loads(x) for x in manifest.read_text().splitlines() if x.strip()]
if len(rows)!=30:
    raise SystemExit(f"expected 30 files, got {len(rows)}")
for row in rows:
    rel=Path(row["file"])
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"unsafe path: {rel}")
    p=out/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(base64.b64decode(row["data_b64"]))
PY

grep -F "$VERSION_TAG" "$SRC/index.html" >/dev/null
grep -F "universeBenchmark" "$SRC/app.js" >/dev/null
grep -F "연구 벤치마크 · TOP-1 vs TOP-6" "$SRC/app.js" >/dev/null
grep -F "Execution Quality:" "$SRC/app.js" >/dev/null
grep -F "net_return" "$SRC/api/assets.js" >/dev/null
node --check "$SRC/app.js" >/dev/null
node --check "$SRC/api/assets.js" >/dev/null
echo "[PASS] source validation"

echo "[2/7] Link Vercel project"
mkdir -p "$SRC/.vercel"
printf '{"projectId":"%s","orgId":"%s"}\n' "$PROJECT_ID" "$TEAM_ID" >"$SRC/.vercel/project.json"

echo "[3/7] Deploy candidate"
set +e
(
  cd "$SRC"
  vercel deploy --prod --skip-domain --yes --scope "$TEAM_SLUG"
) 2>&1 | tee "$WORK/deploy.log"
rc=${PIPESTATUS[0]}
set -e
[ "$rc" -eq 0 ] || fail "candidate deployment failed"

CANDIDATE="$(
python3 - "$WORK/deploy.log" <<'PY'
import re,sys
text=open(sys.argv[1],encoding="utf-8",errors="replace").read()
urls=re.findall(r"https://[A-Za-z0-9.-]+\.vercel\.app",text)
print(urls[-1] if urls else "")
PY
)"
[ -n "$CANDIDATE" ] || fail "candidate URL missing"
echo "[PASS] candidate=$CANDIDATE"

echo "[4/7] Candidate smoke tests"
vcurl(){
  local path="$1" out="$2"
  vercel curl "$CANDIDATE$path" --scope "$TEAM_SLUG" >"$out"
  [ -s "$out" ] || fail "empty response: $path"
}
vcurl "/" "$WORK/index.html"
vcurl "/app.js" "$WORK/app.js"
vcurl "/api/health" "$WORK/health.json"
vcurl "/api/assets?view=control" "$WORK/control.json"
vcurl "/api/dashboard?market=US" "$WORK/us.json"
vcurl "/api/dashboard?market=GLOBAL" "$WORK/global.json"
set +e
vercel curl "$CANDIDATE/api/account" --scope "$TEAM_SLUG" >"$WORK/account.json"
set -e

python3 - "$WORK" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json,sys
root,version=Path(sys.argv[1]),sys.argv[2]
index=(root/"index.html").read_text(encoding="utf-8",errors="replace")
app=(root/"app.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"health.json").read_text())
control=json.loads((root/"control.json").read_text())
account=json.loads((root/"account.json").read_text())
us=json.loads((root/"us.json").read_text())
global_=json.loads((root/"global.json").read_text())

assert version in index
assert "universeBenchmark" in app
assert "연구 벤치마크 · TOP-1 vs TOP-6" in app
assert "Execution Quality:" in app
assert health.get("investment_hub_version")==version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert control.get("schema_version")=="kalman-web-control-v2"
assert account.get("trade_execution") is False
assert not us.get("error")
assert not global_.get("error")
bench=control.get("benchmarks") or {}
assert (bench.get("top1") or {}).get("snapshots",0)>0,bench
assert (bench.get("top6") or {}).get("snapshots",0)>0,bench
rows=control.get("execution_ledger") or []
if rows:
    row=rows[0]
    for key in ("net_return","round_trip_cost_bps","entry_fill_latency_ms","exit_fill_latency_ms"):
        assert key in row,key
print("[PASS] candidate benchmark/API/UI and read-only invariant")
PY

echo "[5/7] Promote candidate"
vercel promote "$CANDIDATE" --yes --scope "$TEAM_SLUG" >/dev/null
echo "[PASS] promoted"

echo "[6/7] Production verification"
vercel curl "$PROD_URL/" --scope "$TEAM_SLUG" >"$WORK/prod-index.html"
vercel curl "$PROD_URL/app.js" --scope "$TEAM_SLUG" >"$WORK/prod-app.js"
vercel curl "$PROD_URL/api/health" --scope "$TEAM_SLUG" >"$WORK/prod-health.json"
vercel curl "$PROD_URL/api/assets?view=control" --scope "$TEAM_SLUG" >"$WORK/prod-control.json"

python3 - "$WORK" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json,sys
root,version=Path(sys.argv[1]),sys.argv[2]
index=(root/"prod-index.html").read_text(encoding="utf-8",errors="replace")
app=(root/"prod-app.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"prod-health.json").read_text())
control=json.loads((root/"prod-control.json").read_text())
assert version in index
assert "universeBenchmark" in app
assert "연구 벤치마크 · TOP-1 vs TOP-6" in app
assert health.get("investment_hub_version")==version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
bench=control.get("benchmarks") or {}
assert (bench.get("top1") or {}).get("snapshots",0)>0
assert (bench.get("top6") or {}).get("snapshots",0)>0
print("[PASS] production v7.4.25 visible; benchmark present; web remains read-only")
PY

echo "[7/7] Done"
echo "DONE: $PROD_URL"
