#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
VERSION_TAG="vNext.7.4.31"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILDER="$ROOT/kalman-toss-gateway/scripts/build_investment_hub_v7431_etf_display_price.py"
MANIFEST="$ROOT/kalman-hub-recovery/v7.4.30/source_manifest.ndjson"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-hub-v7431-${STAMP}"
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

echo "[1/7] Build audited v7.4.30 source"
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
grep -F "tradeSnapshotValidity" "$SRC/app.js" >/dev/null
grep -F "freshnessBadges" "$SRC/app.js" >/dev/null
grep -F "trade_effective_stale" "$SRC/api/assets.js" >/dev/null
grep -F "display_effective_stale" "$SRC/api/assets.js" >/dev/null
grep -F "trade_gate_unchanged:true" "$SRC/api/assets.js" >/dev/null
grep -F "_r5CanonicalLedger" "$SRC/api/assets.js" >/dev/null
grep -F "canonical_ledger_source" "$SRC/api/assets.js" >/dev/null
grep -F "R5_1_CANONICAL_FORWARD_LOG" "$SRC/api/assets.js" >/dev/null
grep -F "augmentAssetsSelectorsFromNeon" "$SRC/api/assets.js" >/dev/null
grep -F "NEON_DASHBOARD_SNAPSHOT" "$SRC/api/assets.js" >/dev/null
grep -F "function renderCommandAccount(" "$SRC/app.js" >/dev/null
grep -F "function renderCommandModel(" "$SRC/app.js" >/dev/null
grep -F "overlayStaleEtfDisplayPrices" "$SRC/lib/assets-payload.js" >/dev/null
grep -F "display_price_source" "$SRC/api/market.js" >/dev/null
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
vcurl "/api/assets" "$WORK/assets.json"
vcurl "/api/market?asset=QLD" "$WORK/market.json"
vcurl "/api/dashboard?market=US" "$WORK/us.json"
vcurl "/api/dashboard?market=KR" "$WORK/kr.json"
vcurl "/api/dashboard?market=CRYPTO" "$WORK/crypto.json"
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
assets=json.loads((root/"assets.json").read_text())
market=json.loads((root/"market.json").read_text())
account=json.loads((root/"account.json").read_text())
us=json.loads((root/"us.json").read_text())
kr=json.loads((root/"kr.json").read_text())
crypto=json.loads((root/"crypto.json").read_text())
global_=json.loads((root/"global.json").read_text())

assert version in index
assert "universeBenchmark" in app
assert "연구 벤치마크 · TOP-1 vs TOP-6" in app
assert "Execution Quality:" in app
assert "function renderCommandAccount(" in app
assert "function renderCommandModel(" in app
assert health.get("investment_hub_version")==version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert control.get("schema_version")=="kalman-web-control-v2"
assert account.get("trade_execution") is False
assert not us.get("error")
assert not crypto.get("error")
assert not global_.get("error")
assert assets.get("selector_source")=="NEON_DASHBOARD_SNAPSHOT",assets.get("selector_source")
assert assets.get("kr_selector_source")=="NEON_DASHBOARD_SNAPSHOT",assets.get("kr_selector_source")
assert (assets.get("selector_read_model") or {}).get("canonical") is True
assert (assets.get("kr_selector_read_model") or {}).get("canonical") is True
assert assets.get("etf_display_price_source")=="YAHOO_PUBLIC_CONTEXT",assets.get("etf_display_price_source")
assert set(assets.get("etf_display_price_symbols") or [])=={"QQQ","QLD"},assets.get("etf_display_price_symbols")
for sym in ("QQQ","QLD"):
    a=(assets.get("assets") or {}).get(sym) or {}
    assert (a.get("price") or {}).get("display_source")=="YAHOO_PUBLIC_CONTEXT",(sym,a.get("price"))
    assert (a.get("freshness") or {}).get("stale") is True,(sym,a.get("freshness"))
    assert (a.get("freshness") or {}).get("modelSnapshotStale") is True,(sym,a.get("freshness"))
    assert (a.get("decision") or {}).get("state")=="WAIT",(sym,a.get("decision"))
assert "STALE_ETF_SNAPSHOT" in (((assets.get("assets") or {}).get("QLD") or {}).get("decision") or {}).get("reasonCodes",[])
assert market.get("display_price_source")=="YAHOO_PUBLIC_CONTEXT",market
assert set(market.get("display_price_symbols") or [])=={"QQQ","QLD"},market
assert (market.get("model_snapshot_stale") or {}).get("QQQ") is True
assert (market.get("model_snapshot_stale") or {}).get("QLD") is True
us_src=((us.get("payload") or {}).get("source_payload") or {})
kr_src=((kr.get("payload") or {}).get("source_payload") or {})
assert (assets.get("today_selector") or {}).get("selected_symbol")==((us_src.get("today_selector") or {}).get("selected_symbol"))
assert str((assets.get("today_selector") or {}).get("as_of_utc"))==str((us_src.get("today_selector") or {}).get("as_of_utc"))
assert len(assets.get("model_universe") or {})>=80
assert str((assets.get("kr_selector") or {}).get("as_of_market_date"))[:10]==str(kr_src.get("as_of_market_date"))[:10]
for x in (us,crypto,global_):
    assert "trade_effective_stale" in x
    assert "display_effective_stale" in x
    assert x.get("effective_stale") is x.get("trade_effective_stale")
    fc=x.get("freshness_contract") or {}
    assert fc.get("version")=="kalman-freshness-v1"
    assert fc.get("trade_gate_unchanged") is True
assert (crypto.get("freshness_contract") or {}).get("display_basis")=="PIPELINE_GENERATED_AT"
assert (global_.get("freshness_contract") or {}).get("display_basis")=="PIPELINE_GENERATED_AT"
assert (us.get("freshness_contract") or {}).get("display_basis")=="TRADE_STALE_AFTER"
assert us.get("canonical_ledger_source") is True, us.get("canonical_ledger_error")
src=(us.get("payload") or {}).get("source_payload") or {}
ledger=src.get("r5_shadow_ledger") or {}
annual=ledger.get("annual_2026") or {}
readmodel=src.get("r5_ledger_read_model") or {}
assert readmodel.get("source")=="strategy_ledger",readmodel
assert readmodel.get("canonical") is True,readmodel
assert len(annual.get("trades") or [])>=268,len(annual.get("trades") or [])
assert len((annual.get("reconstructed") or {}).get("trades") or [])==251
assert len((annual.get("forward") or {}).get("trades") or [])>=17
open_rows=[t for t in ((annual.get("forward") or {}).get("trades") or []) if not t.get("exit_time")]
assert open_rows, "expected at least one open forward trade"
assert all(t.get("return_pct") is None for t in open_rows), open_rows
assert len(annual.get("events") or [])>0
assert (ledger.get("summary") or {}).get("last_event") is not None
assert us.get("canonical_ledger_source") is True,us.get("canonical_ledger_error")
src=(us.get("payload") or {}).get("source_payload") or {}
ledger=src.get("r5_shadow_ledger") or {}
annual=ledger.get("annual_2026") or {}
assert len(annual.get("trades") or [])>=268
assert len((annual.get("reconstructed") or {}).get("trades") or [])==251
assert len((annual.get("forward") or {}).get("trades") or [])>=17
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
vercel curl "$PROD_URL/api/assets" --scope "$TEAM_SLUG" >"$WORK/prod-assets.json"
vercel curl "$PROD_URL/api/market?asset=QLD" --scope "$TEAM_SLUG" >"$WORK/prod-market.json"
vercel curl "$PROD_URL/api/dashboard?market=US" --scope "$TEAM_SLUG" >"$WORK/prod-us.json"
vercel curl "$PROD_URL/api/dashboard?market=KR" --scope "$TEAM_SLUG" >"$WORK/prod-kr.json"
vercel curl "$PROD_URL/api/dashboard?market=CRYPTO" --scope "$TEAM_SLUG" >"$WORK/prod-crypto.json"
vercel curl "$PROD_URL/api/dashboard?market=GLOBAL" --scope "$TEAM_SLUG" >"$WORK/prod-global.json"

python3 - "$WORK" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json,sys
root,version=Path(sys.argv[1]),sys.argv[2]
index=(root/"prod-index.html").read_text(encoding="utf-8",errors="replace")
app=(root/"prod-app.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"prod-health.json").read_text())
control=json.loads((root/"prod-control.json").read_text())
assets=json.loads((root/"prod-assets.json").read_text())
market=json.loads((root/"prod-market.json").read_text())
crypto=json.loads((root/"prod-crypto.json").read_text())
global_=json.loads((root/"prod-global.json").read_text())
us=json.loads((root/"prod-us.json").read_text())
kr=json.loads((root/"prod-kr.json").read_text())
assert version in index
assert "universeBenchmark" in app
assert "연구 벤치마크 · TOP-1 vs TOP-6" in app
assert "function renderCommandAccount(" in app
assert "function renderCommandModel(" in app
assert health.get("investment_hub_version")==version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert assets.get("selector_source")=="NEON_DASHBOARD_SNAPSHOT"
assert assets.get("kr_selector_source")=="NEON_DASHBOARD_SNAPSHOT"
assert (assets.get("selector_read_model") or {}).get("canonical") is True
assert (assets.get("kr_selector_read_model") or {}).get("canonical") is True
assert assets.get("etf_display_price_source")=="YAHOO_PUBLIC_CONTEXT"
assert set(assets.get("etf_display_price_symbols") or [])=={"QQQ","QLD"}
for sym in ("QQQ","QLD"):
    a=(assets.get("assets") or {}).get(sym) or {}
    assert (a.get("price") or {}).get("display_source")=="YAHOO_PUBLIC_CONTEXT"
    assert (a.get("freshness") or {}).get("stale") is True
    assert (a.get("freshness") or {}).get("modelSnapshotStale") is True
    assert (a.get("decision") or {}).get("state")=="WAIT"
assert "STALE_ETF_SNAPSHOT" in (((assets.get("assets") or {}).get("QLD") or {}).get("decision") or {}).get("reasonCodes",[])
assert market.get("display_price_source")=="YAHOO_PUBLIC_CONTEXT"
assert set(market.get("display_price_symbols") or [])=={"QQQ","QLD"}
assert (market.get("model_snapshot_stale") or {}).get("QQQ") is True
assert (market.get("model_snapshot_stale") or {}).get("QLD") is True
us_src=((us.get("payload") or {}).get("source_payload") or {})
kr_src=((kr.get("payload") or {}).get("source_payload") or {})
assert str((assets.get("today_selector") or {}).get("as_of_utc"))==str((us_src.get("today_selector") or {}).get("as_of_utc"))
assert str((assets.get("kr_selector") or {}).get("as_of_market_date"))[:10]==str(kr_src.get("as_of_market_date"))[:10]
for x in (crypto,global_):
    assert x.get("effective_stale") is x.get("trade_effective_stale")
    assert "display_effective_stale" in x
    assert (x.get("freshness_contract") or {}).get("trade_gate_unchanged") is True
    assert (x.get("freshness_contract") or {}).get("display_basis")=="PIPELINE_GENERATED_AT"
assert us.get("canonical_ledger_source") is True,us.get("canonical_ledger_error")
src=(us.get("payload") or {}).get("source_payload") or {}
ledger=src.get("r5_shadow_ledger") or {}
annual=ledger.get("annual_2026") or {}
readmodel=src.get("r5_ledger_read_model") or {}
assert readmodel.get("source")=="strategy_ledger"
assert readmodel.get("canonical") is True
assert len(annual.get("trades") or [])>=268
assert len((annual.get("reconstructed") or {}).get("trades") or [])==251
assert len((annual.get("forward") or {}).get("trades") or [])>=17
open_rows=[t for t in ((annual.get("forward") or {}).get("trades") or []) if not t.get("exit_time")]
assert open_rows
assert all(t.get("return_pct") is None for t in open_rows),open_rows
assert len(annual.get("events") or [])>0
bench=control.get("benchmarks") or {}
assert (bench.get("top1") or {}).get("snapshots",0)>0
assert (bench.get("top6") or {}).get("snapshots",0)>0
print("[PASS] production v7.4.30 visible; command renderers restored; US/KR/R5.1 sources preserved; web remains read-only")
PY

echo "[7/7] Done"
echo "DONE: $PROD_URL"
