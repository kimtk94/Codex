#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
KR_PROJECT_ID="prj_1nWivN1icAZCBF9CVKWeI6nYQhhp"
US_PROJECT_ID="prj_xvEw2HKkknxRSSj8s7mtATcz4zz2"
KR_PROD_URL="https://kalman-investment-hub-kr.vercel.app"
US_PROD_URL="https://kalman-investment-hub-us.vercel.app"
CANONICAL_API_ORIGIN="https://kalman-investment-hub-v2.vercel.app"
VERSION_TAG="vNext.7.4.35"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_KPI_API="$ROOT/kalman-toss-gateway/web/market-sites/shared/market-kpis.js"
BUILDER="$ROOT/kalman-toss-gateway/scripts/build_investment_hub_v7435_dedicated_sites.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-market-sites-v7435-${STAMP}"
mkdir -p "$WORK"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }
need vercel
need python3
need node

echo "[0/5] Authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel authenticated"

echo "[1/5] Build audited KR/US source"
python3 "$BUILDER"

decode_manifest(){
  local manifest="$1" out="$2"
  rm -rf "$out"
  mkdir -p "$out"
  python3 - "$manifest" "$out" <<'PY'
from pathlib import Path
import base64,json,sys
manifest,out=Path(sys.argv[1]),Path(sys.argv[2])
rows=[json.loads(x) for x in manifest.read_text().splitlines() if x.strip()]
if not rows:
    raise SystemExit("empty source manifest")
for row in rows:
    rel=Path(row["file"])
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"unsafe path: {rel}")
    p=out/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(base64.b64decode(row["data_b64"]))
PY
}

vcurl(){
  local base="$1" path="$2" out="$3"
  vercel curl "$base$path" --scope "$TEAM_SLUG" >"$out"
  [ -s "$out" ] || fail "empty response: $base$path"
}

prepare_static_proxy(){
  local src="$1"
  rm -rf "$src/api"
  mkdir -p "$src/api"
  cp "$LOCAL_KPI_API" "$src/api/market-kpis.js"
  cat >"$src/vercel.json" <<JSON
{
  "rewrites": [
    {
      "source": "/market-pulse",
      "destination": "/api/market-kpis"
    },
    {
      "source": "/api/:path*",
      "destination": "$CANONICAL_API_ORIGIN/api/:path*"
    }
  ]
}
JSON
}

smoke_market(){
  local market="$1" base="$2" dir="$3"
  vcurl "$base" "/" "$dir/index.html"
  vcurl "$base" "/api/health" "$dir/health.json"
  vcurl "$base" "/api/dashboard?market=$market" "$dir/dashboard.json"
  vcurl "$base" "/market-pulse?market=$market" "$dir/market-pulse.json"
  if [ "$market" = "KR" ]; then
    vcurl "$base" "/compact.js" "$dir/frontend.js"
    vcurl "$base" "/core.js" "$dir/core.js"
  else
    vcurl "$base" "/app.js" "$dir/frontend.js"
    vcurl "$base" "/api/assets?view=control" "$dir/control.json"
  fi
  python3 - "$market" "$dir" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json,sys
market,root,version=sys.argv[1],Path(sys.argv[2]),sys.argv[3]
index=(root/"index.html").read_text(encoding="utf-8",errors="replace")
front=(root/"frontend.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"health.json").read_text())
dash=json.loads((root/"dashboard.json").read_text())
pulse=json.loads((root/"market-pulse.json").read_text())
assert pulse.get("schema_version")=="kalman-market-pulse-v2",pulse
assert pulse.get("market")==market,pulse
assert pulse.get("read_only") is True and pulse.get("trade_signal_input") is False,pulse
assert len(pulse.get("items") or [])==6,pulse
assert "regimeSummaryHtml" in front, "market regime summary missing"
assert "MARKET REGIME" in front, "market regime label missing"
assert "descriptive context only" in front, "regime safety marker missing"
if market=="US":
    keys={x.get("key") for x in pulse.get("items") or []}
    assert {"US2Y","US10Y","US2S10S"} <= keys,keys
    assert all(next(x for x in pulse["items"] if x["key"]==k).get("status")=="READY" for k in ("US2Y","US10Y","US2S10S")),pulse
else:
    keys={x.get("key") for x in pulse.get("items") or []}
    assert {"KR3Y","KR10Y","KR3S10S"} <= keys,keys
    assert all(next(x for x in pulse["items"] if x["key"]==k).get("status")=="READY" for k in ("KR3Y","KR10Y","KR3S10S")),pulse
assert str(health.get("investment_hub_version") or "").startswith("vNext."),health.get("investment_hub_version")
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert dash.get("market")==market,dash.get("market")
assert dash.get("status")=="READY",dash.get("status")
assert not dash.get("error")
for u in (
    "https://kalman-investment-hub-v2.vercel.app",
    "https://kalman-investment-hub-kr.vercel.app",
    "https://kalman-investment-hub-us.vercel.app",
):
    assert u in front,u
if market=="KR":
    core=(root/"core.js").read_text(encoding="utf-8",errors="replace")
    assert "Kalman · KR Investment Hub" in index
    assert 'siteNav("KR")' in front
    assert "현재 OPEN" in front and "오늘 Signal" in front and "KR Universe" in front
    assert "STRICT vs BUFFER" in core and "strategyCompareHtml" in core
    payload=dash.get("payload") or {}
    assert len(payload.get("top3") or [])==3
    assert len(payload.get("assets") or [])>=50
else:
    assert "Kalman · US Investment Hub" in index
    assert "siteNav('US')" in front
    for marker in ("Research Benchmark · TOP-1 vs TOP-6","R5.1 2026 Ledger","FORWARD SHADOW","RECONSTRUCTED · 2026","US SESSION · KST DATE","NEXT ACTION","NEXT UPDATE","sessionStatusHtml"):
        assert marker in front,marker
    control=json.loads((root/"control.json").read_text())
    bench=control.get("benchmarks") or {}
    assert (bench.get("top1") or {}).get("snapshots",0)>0,bench
    assert (bench.get("top6") or {}).get("snapshots",0)>0,bench
    assert dash.get("canonical_ledger_source") is True,dash.get("canonical_ledger_error")
    annual=((((dash.get("payload") or {}).get("source_payload") or {}).get("r5_shadow_ledger") or {}).get("annual_2026") or {})
    assert len((annual.get("reconstructed") or {}).get("trades") or [])>0
    fw=(annual.get("forward") or {})
    assert len(fw.get("trades") or [])>0
    opens=[t for t in (fw.get("trades") or []) if not t.get("exit_time")]
    assert all(t.get("return_pct") is None for t in opens),opens
print(f"[PASS] {market} smoke")
PY
}

deploy_market(){
  local market="$1" project_id="$2" prod_url="$3" manifest="$4"
  local lower="$(echo "$market" | tr '[:upper:]' '[:lower:]')"
  local src="$WORK/${lower}-source" testdir="$WORK/${lower}-candidate" proddir="$WORK/${lower}-prod"
  decode_manifest "$manifest" "$src"
  prepare_static_proxy "$src"
  mkdir -p "$src/.vercel"
  printf '{"projectId":"%s","orgId":"%s"}\n' "$project_id" "$TEAM_ID" >"$src/.vercel/project.json"

  echo "[2/5][$market] Deploy candidate"
  set +e
  (
    cd "$src"
    VERCEL_PROJECT_ID="$project_id" VERCEL_ORG_ID="$TEAM_ID" vercel deploy --prod --skip-domain --yes --scope "$TEAM_SLUG"
  ) 2>&1 | tee "$WORK/${lower}-deploy.log"
  rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -eq 0 ] || fail "$market candidate deployment failed"

  local candidate
  candidate="$(python3 - "$WORK/${lower}-deploy.log" <<'PY'
import re,sys
text=open(sys.argv[1],encoding="utf-8",errors="replace").read()
urls=re.findall(r"https://[A-Za-z0-9.-]+\.vercel\.app",text)
print(urls[-1] if urls else "")
PY
)"
  [ -n "$candidate" ] || fail "$market candidate URL missing"
  echo "[PASS][$market] candidate=$candidate"

  mkdir -p "$testdir"
  echo "[3/5][$market] Candidate smoke"
  smoke_market "$market" "$candidate" "$testdir"

  echo "[4/5][$market] Promote"
  vercel promote "$candidate" --yes --scope "$TEAM_SLUG" >/dev/null
  echo "[PASS][$market] promoted"

  mkdir -p "$proddir"
  echo "[5/5][$market] Production verification"
  smoke_market "$market" "$prod_url" "$proddir"
}

deploy_market "KR" "$KR_PROJECT_ID" "$KR_PROD_URL" "$ROOT/kalman-hub-recovery/v7.4.35/kr/source_manifest.ndjson"
deploy_market "US" "$US_PROJECT_ID" "$US_PROD_URL" "$ROOT/kalman-hub-recovery/v7.4.35/us/source_manifest.ndjson"

echo "[PASS] KR/US dedicated sites v7.4.35 production deployment complete"
