from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7425_persistent_benchmark.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.25/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.26"
TARGET = "vNext.7.4.26"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.25 base manifest was not generated")


def decode_manifest(manifest: Path, out: Path) -> None:
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 30:
        raise SystemExit(f"expected 30 files, got {len(rows)}")
    for row in rows:
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(row["data_b64"]))


def patch_api(src: Path) -> None:
    p = src / "api/assets.js"
    text = p.read_text(encoding="utf-8")
    old = """async function dashboard(req,res){
  const market=String(q(req,'market')||'').toUpperCase();
  if(!DB_MARKETS.has(market))return res.status(400).json({error:'INVALID_MARKET'});
  if(!process.env.DATABASE_URL_READER)return res.status(503).json({error:'DB_NOT_CONFIGURED'});
  try{
    const {neon}=await import('@neondatabase/serverless');
    const sql=neon(process.env.DATABASE_URL_READER);
    const rows=await sql`SELECT market,run_id,generated_at,data_as_of,model_version,stale_after,status,payload FROM v_latest_dashboard_snapshot WHERE market=${market} LIMIT 1`;
    if(!rows.length)return res.status(404).json({error:'NO_SNAPSHOT',market});
    const x=rows[0],stale=Date.now()>new Date(x.stale_after).getTime();
    res.setHeader('Cache-Control','no-store');
    return res.status(200).json({...x,effective_stale:stale});
  }catch(e){return res.status(500).json({error:'DB_READ_FAILED',detail:String(e?.message||e)});}
}"""
    new = """async function dashboard(req,res){
  const market=String(q(req,'market')||'').toUpperCase();
  if(!DB_MARKETS.has(market))return res.status(400).json({error:'INVALID_MARKET'});
  if(!process.env.DATABASE_URL_READER)return res.status(503).json({error:'DB_NOT_CONFIGURED'});
  try{
    const {neon}=await import('@neondatabase/serverless');
    const sql=neon(process.env.DATABASE_URL_READER);
    const rows=await sql`SELECT market,run_id,generated_at,data_as_of,model_version,stale_after,status,payload FROM v_latest_dashboard_snapshot WHERE market=${market} LIMIT 1`;
    if(!rows.length)return res.status(404).json({error:'NO_SNAPSHOT',market});
    const x=rows[0],now=Date.now();
    const staleAt=new Date(x.stale_after).getTime();
    const generatedAt=new Date(x.generated_at).getTime();
    const tradeStale=!Number.isFinite(staleAt)||now>staleAt;
    const displayWindowMinutes=(market==='CRYPTO'||market==='GLOBAL')?90:null;
    const generatedAgeMinutes=Number.isFinite(generatedAt)?Math.max(0,(now-generatedAt)/60000):null;
    const displayStale=displayWindowMinutes==null
      ?tradeStale
      :(generatedAgeMinutes==null||generatedAgeMinutes>displayWindowMinutes);
    res.setHeader('Cache-Control','no-store');
    return res.status(200).json({
      ...x,
      effective_stale:tradeStale,
      trade_effective_stale:tradeStale,
      display_effective_stale:displayStale,
      freshness_contract:{
        version:'kalman-freshness-v1',
        trade_basis:'STALE_AFTER',
        display_basis:displayWindowMinutes==null?'TRADE_STALE_AFTER':'PIPELINE_GENERATED_AT',
        display_max_age_minutes:displayWindowMinutes,
        generated_age_minutes:generatedAgeMinutes,
        trade_gate_unchanged:true
      }
    });
  }catch(e){return res.status(500).json({error:'DB_READ_FAILED',detail:String(e?.message||e)});}
}"""
    if old not in text:
        raise SystemExit("dashboard API anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")

    old = """function snapshotValidity(j){
  var dataTs=Date.parse(j&&j.data_as_of||'');
  var staleTs=Date.parse(j&&j.stale_after||'');
  var age=Number.isFinite(dataTs)?Math.max(0,(Date.now()-dataTs)/60000):Infinity;
  var expired=(j&&typeof j.effective_stale==='boolean')?j.effective_stale:(Number.isFinite(staleTs)?Date.now()>=staleTs:true);
  return {valid:expired===false,expired:expired!==false,ageMinutes:age,validUntil:Number.isFinite(staleTs)?staleTs:null};
}
function executionFreshness(us){
  var sv=snapshotValidity(us);
  return {fresh:sv.valid&&Number.isFinite(sv.ageMinutes)&&sv.ageMinutes<=EXECUTION_FRESH_MINUTES,ageMinutes:sv.ageMinutes,snapshotValid:sv.valid};
}"""
    new = """function tradeSnapshotValidity(j){
  var dataTs=Date.parse(j&&j.data_as_of||'');
  var staleTs=Date.parse(j&&j.stale_after||'');
  var age=Number.isFinite(dataTs)?Math.max(0,(Date.now()-dataTs)/60000):Infinity;
  var expired=(j&&typeof j.trade_effective_stale==='boolean')
    ?j.trade_effective_stale
    :((j&&typeof j.effective_stale==='boolean')?j.effective_stale:(Number.isFinite(staleTs)?Date.now()>=staleTs:true));
  return {valid:expired===false,expired:expired!==false,ageMinutes:age,validUntil:Number.isFinite(staleTs)?staleTs:null};
}
function snapshotValidity(j){
  var trade=tradeSnapshotValidity(j);
  var displayExpired=(j&&typeof j.display_effective_stale==='boolean')?j.display_effective_stale:trade.expired;
  return {valid:displayExpired===false,expired:displayExpired!==false,ageMinutes:trade.ageMinutes,validUntil:trade.validUntil};
}
function freshnessBadges(j){
  var display=snapshotValidity(j),trade=tradeSnapshotValidity(j);
  return badge(display.valid?'데이터 최신':'데이터 지연',display.valid?'ok':'warn')+' '+
    badge(trade.valid?'거래 유효':'거래 만료',trade.valid?'ok':'warn');
}
function executionFreshness(us){
  var sv=tradeSnapshotValidity(us);
  return {fresh:sv.valid&&Number.isFinite(sv.ageMinutes)&&sv.ageMinutes<=EXECUTION_FRESH_MINUTES,ageMinutes:sv.ageMinutes,snapshotValid:sv.valid};
}"""
    if old not in text:
        raise SystemExit("snapshot validity anchor missing")
    text = text.replace(old, new, 1)

    start = text.find("function healthRow(label,state,detail){")
    end = text.find("\nfunction benchmarkMetric(", start)
    if start < 0 or end < 0:
        raise SystemExit("renderCommandHealth anchors missing")
    replacement = """function healthFreshnessState(j){
  var display=snapshotValidity(j),trade=tradeSnapshotValidity(j);
  return '<span class="health-dot '+(display.valid?'good-dot':'warn-dot')+'"></span>'+
    (display.valid?'최신':'지연')+' · '+(trade.valid?'거래 유효':'거래 만료');
}
function healthRow(label,state,detail){return '<div class="health-row"><span>'+label+'</span><b>'+state+'</b><small>'+detail+'</small></div>';}
function renderCommandHealth(us,kr,cr,h){
  kalmanCommandState.health=h;kalmanCommandState.us=us;kalmanCommandState.kr=kr;kalmanCommandState.crypto=cr;
  var box=$('#commandHealth');if(!box)return;
  box.className='';
  var usv=snapshotValidity(us),krv=snapshotValidity(kr),crv=snapshotValidity(cr);
  var account=kalmanCommandState.account,bot=botState(account);
  var windowKnown=Boolean(bot&&typeof bot.usFractionalOrderWindowOpen==='boolean');
  var windowState=windowKnown?(bot.usFractionalOrderWindowOpen?'주문 가능':'마감'):'확인 불가';
  var windowKind=windowKnown&&bot.usFractionalOrderWindowOpen?'good-dot':'warn-dot';
  box.innerHTML=[
    healthRow('US 데이터',healthFreshnessState(us),'기준 '+time(us&&us.data_as_of)+' · trade stale '+time(us&&us.stale_after)),
    healthRow('KR 데이터',healthFreshnessState(kr),'기준 '+time(kr&&kr.data_as_of)+' · trade stale '+time(kr&&kr.stale_after)),
    healthRow('Crypto 데이터',healthFreshnessState(cr),'pipeline '+time(cr&&cr.generated_at)+' · candle '+time(cr&&cr.data_as_of)),
    healthRow('미국 주문시간','<span class="health-dot '+windowKind+'"></span>'+windowState,windowKnown?'Toss 시장 캘린더':'Toss 연결 필요')
  ].join('');
  var head=$('#headerDataState');
  if(head){var ok=usv.valid&&krv.valid&&crv.valid;head.className='pill '+(ok?'ok':'warn');head.textContent=ok?'데이터 정상':'데이터 확인 필요';}
}
"""
    text = text[:start] + replacement + text[end:]

    text = text.replace("${staleBadge(j.effective_stale)} ${badge(j.model_version||'CRYPTO')}", "${freshnessBadges(j)} ${badge(j.model_version||'CRYPTO')}", 1)
    text = text.replace("${staleBadge(j.effective_stale)} ${badge(s.market_risk||'US')} ${badge(s.primary_lineage||j.model_version||'MODEL')}", "${freshnessBadges(j)} ${badge(s.market_risk||'US')} ${badge(s.primary_lineage||j.model_version||'MODEL')}", 1)
    text = text.replace("${staleBadge(j.effective_stale)} ${badge(s.regime||'KR')} ${s.overall_action_label?badge(s.overall_action_label,'ok'):''}", "${freshnessBadges(j)} ${badge(s.regime||'KR')} ${s.overall_action_label?badge(s.overall_action_label,'ok'):''}", 1)
    text = text.replace("'<section class=\"us-pane active\" data-us-pane=\"overview\"><div class=\"summary\">'+staleBadge(j.effective_stale)+' '", "'<section class=\"us-pane active\" data-us-pane=\"overview\"><div class=\"summary\">'+freshnessBadges(j)+' '", 1)

    old_global = """    const sv=snapshotValidity(x);
    return '<div class="card"><div class="section-title"><h3>'+(k==='KR'?'한국장':k==='US'?'미국장':'Crypto')+'</h3>'+badge(sv.valid?'스냅샷 유효':'스냅샷 만료',sv.valid?'ok':'warn')+'</div><div class="kpi">'+esc(lead||'—')+'</div><div class="small">'+time(x.data_as_of)+'</div></div>';"""
    new_global = """    const sv=snapshotValidity(x),tv=tradeSnapshotValidity(x);
    return '<div class="card"><div class="section-title"><h3>'+(k==='KR'?'한국장':k==='US'?'미국장':'Crypto')+'</h3><span>'+badge(sv.valid?'데이터 최신':'데이터 지연',sv.valid?'ok':'warn')+' '+badge(tv.valid?'거래 유효':'거래 만료',tv.valid?'ok':'warn')+'</span></div><div class="kpi">'+esc(lead||'—')+'</div><div class="small">'+time(x.data_as_of)+'</div></div>';"""
    if old_global not in text:
        raise SystemExit("global freshness card anchor missing")
    text = text.replace(old_global, new_global, 1)

    p.write_text(text, encoding="utf-8")


def patch_style(src: Path) -> None:
    p = src / "style.css"
    text = p.read_text(encoding="utf-8")
    addition = """
/* vNext.7.4.26 — display freshness vs trade freshness */
.health-row{grid-template-columns:82px 132px 1fr}
@media(max-width:600px){.health-row{grid-template-columns:76px 118px 1fr;gap:5px}}
"""
    if "vNext.7.4.26 — display freshness vs trade freshness" not in text:
        text += addition
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.25" not in text:
            raise SystemExit(f"v7.4.25 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.25", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")

    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    style = (src / "style.css").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    for marker in (
        "trade_effective_stale",
        "display_effective_stale",
        "trade_gate_unchanged:true",
        "PIPELINE_GENERATED_AT",
        "display_max_age_minutes",
    ):
        if marker not in assets:
            raise SystemExit(f"freshness API missing {marker}")

    for marker in (
        "tradeSnapshotValidity",
        "freshnessBadges",
        "데이터 최신",
        "거래 만료",
        "healthFreshnessState",
        "universeBenchmark",
        "Execution Quality:",
    ):
        if marker not in app:
            raise SystemExit(f"freshness UI missing {marker}")

    if "vNext.7.4.26 — display freshness vs trade freshness" not in style:
        raise SystemExit("freshness CSS missing")

    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "source_files": len([x for x in src.rglob("*") if x.is_file()]),
        "api_functions": len(api),
        "display_trade_freshness_split": True,
        "trade_effective_stale_backward_compatible": True,
        "crypto_global_display_window_minutes": 90,
        "trade_gate_unchanged": True,
        "persistent_universe_benchmark": True,
        "execution_quality_ui": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.25",
    }


def emit_source_manifest(src: Path, out: Path) -> None:
    rows = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({
            "file": p.relative_to(src).as_posix(),
            "data_b64": base64.b64encode(p.read_bytes()).decode("ascii"),
        }, separators=(",", ":"), ensure_ascii=False))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    build_base()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7426-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_api(src)
        patch_app(src)
        patch_style(src)
        patch_versions(src)
        report = validate(src)
        manifest = OUT_DIR / "source_manifest.ndjson"
        emit_source_manifest(src, manifest)
        report["source_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (OUT_DIR / "build_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
