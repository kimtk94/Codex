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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7426_freshness_split.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.26/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.27"
TARGET = "vNext.7.4.27"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.26 base manifest was not generated")


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
    start = text.find("async function dashboard(req,res){")
    end = text.find("\nmodule.exports=async(req,res)=>{", start)
    if start < 0 or end < 0:
        raise SystemExit("dashboard function anchors missing")

    replacement = r"""
function _r5n(v){
  const x=Number(v);
  return Number.isFinite(x)?x:null;
}
function _r5meta(v){
  return v&&typeof v==='object'&&!Array.isArray(v)?v:{};
}
function _r5trade(row){
  const m=_r5meta(row.metadata);
  const provenance=String(m.provenance||'');
  return {
    trade_id:String(row.trade_id||''),
    original_trade_id:m.original_trade_id||null,
    symbol:String(row.symbol||''),
    strategy_version:String(row.strategy_version||'R5.1_BASE_HGB'),
    model_version:String(row.model_version||'R5.1_BASE_HGB'),
    entry_time:row.entry_time||null,
    entry_price:_r5n(row.entry_price),
    exit_time:row.exit_time||null,
    exit_price:_r5n(row.exit_price),
    return_pct:_r5n(row.return_pct),
    exit_reason:row.exit_reason||null,
    ledger_type:row.ledger_type||null,
    provenance,
    prospective:m.prospective===true,
    shadow_only:m.shadow_only!==false,
    trade_execution:false,
    execution:false,
    status:m.status||((row.exit_time&&row.exit_price!=null)?'CLOSED':'OPEN'),
    position_weight:_r5n(m.position_weight),
    score:_r5n(m.score),
    raw_return:_r5n(m.raw_return),
    gross_weighted_return:_r5n(m.gross_weighted_return),
    net10_return:_r5n(m.net10_return!=null?m.net10_return:row.return_pct),
    cost_bps:_r5n(m.cost_bps!=null?m.cost_bps:10),
    expected_seq:m.expected_seq==null?null:Number(m.expected_seq),
    expected_exit_seq:m.expected_exit_seq==null?null:Number(m.expected_exit_seq),
    model_freeze_sha256:m.model_freeze_sha256||null
  };
}
function _r5summary(trades){
  const closed=trades.filter(t=>t.exit_time&&_r5n(t.return_pct)!=null);
  const open=trades.filter(t=>!t.exit_time);
  let compound=1;
  let sum=0;
  for(const t of closed){
    const r=_r5n(t.return_pct);
    compound*=1+r;
    sum+=r;
  }
  const eventTimes=[];
  for(const t of trades){
    if(t.entry_time)eventTimes.push(new Date(t.entry_time).getTime());
    if(t.exit_time)eventTimes.push(new Date(t.exit_time).getTime());
  }
  const validTimes=eventTimes.filter(Number.isFinite);
  return {
    first_entry:trades.length?trades[0].entry_time:null,
    last_event:validTimes.length?new Date(Math.max(...validTimes)).toISOString():null,
    trade_count:trades.length,
    closed_count:closed.length,
    open_count:open.length,
    open_symbols:open.map(t=>t.symbol),
    closed_mean_return_pct:closed.length?(sum/closed.length)*100:null,
    closed_compound_return_pct:closed.length?(compound-1)*100:null,
    return_semantics:'POSITION_WEIGHTED_NET10_DECIMAL_COMPOUNDED'
  };
}
function _r5events(trades){
  const out=[];
  for(const t of trades){
    const recon=t.provenance==='R5_1_RECONSTRUCTED_2026';
    if(t.entry_time&&t.entry_price!=null){
      out.push({
        time:t.entry_time,price:t.entry_price,signal:'BUY',symbol:t.symbol,
        trade_id:t.trade_id,source:t.provenance,provenance:t.provenance,
        event_type:recon?'R5_1_RECON_ENTER':'R5_1_FORWARD_ENTER',
        prospective:t.prospective===true
      });
    }
    if(t.exit_time&&t.exit_price!=null){
      out.push({
        time:t.exit_time,price:t.exit_price,signal:'SELL',symbol:t.symbol,
        trade_id:t.trade_id,source:t.provenance,provenance:t.provenance,
        event_type:recon?'R5_1_RECON_EXIT':'R5_1_FORWARD_EXIT',
        exit_reason:t.exit_reason||'EXPECTED_SEQ_PLUS_4',
        prospective:t.prospective===true
      });
    }
  }
  out.sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
  return out;
}
async function _r5CanonicalLedger(sql){
  const rows=await sql`
    SELECT trade_id::text,symbol,strategy_version,model_version,
           entry_time,entry_price,exit_time,exit_price,return_pct,
           exit_reason,ledger_type,metadata
    FROM strategy_ledger
    WHERE market='US'
      AND strategy_version='R5.1_BASE_HGB'
      AND (
        (ledger_type='BACKTEST' AND metadata->>'provenance'='R5_1_RECONSTRUCTED_2026')
        OR
        (ledger_type='LIVE_SHADOW' AND metadata->>'provenance'='R5_1_CANONICAL_FORWARD_LOG')
      )
    ORDER BY entry_time,trade_id
  `;
  const all=rows.map(_r5trade);
  const recon=all.filter(t=>t.provenance==='R5_1_RECONSTRUCTED_2026');
  const forward=all.filter(t=>t.provenance==='R5_1_CANONICAL_FORWARD_LOG');
  const reconEvents=_r5events(recon),forwardEvents=_r5events(forward);
  const annualTrades=[...recon,...forward].sort((a,b)=>Date.parse(a.entry_time)-Date.parse(b.entry_time));
  const annualEvents=[...reconEvents,...forwardEvents].sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
  const reconSummary=_r5summary(recon),forwardSummary=_r5summary(forward);
  return {
    schema_version:'r5-shadow-lifecycle-v0.3-neon-readmodel',
    model_version:'R5.1_BASE_HGB',
    strategy_version:'R5.1_BASE_HGB',
    ledger_type:'LIVE_SHADOW',
    shadow_only:true,
    execution:false,
    generated_at:new Date().toISOString(),
    trades:forward,
    events:forwardEvents,
    summary:forwardSummary,
    annual_2026:{
      schema_version:'r5-annual-ledger-v1-neon-readmodel',
      calendar_year:2026,
      reconstructed_boundary:forward.length?forward[0].entry_time:null,
      official_ytd:false,
      warning:'RECONSTRUCTED segment is in-sample replay; only Forward is prospective SHADOW.',
      reconstructed:{trades:recon,events:reconEvents,summary:reconSummary},
      forward:{trades:forward,events:forwardEvents,summary:forwardSummary},
      trades:annualTrades,
      events:annualEvents
    }
  };
}

async function dashboard(req,res){
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

    let payload=x.payload&&typeof x.payload==='object'?{...x.payload}:x.payload;
    let canonicalLedgerSource=false,canonicalLedgerError=null;
    if(market==='US'&&payload&&typeof payload==='object'){
      try{
        const ledger=await _r5CanonicalLedger(sql);
        const source=payload.source_payload&&typeof payload.source_payload==='object'
          ?{...payload.source_payload}:{};
        source.r5_shadow_ledger=ledger;
        source.r5_ledger_read_model={
          source:'strategy_ledger',
          canonical:true,
          reconstructed_trades:ledger.annual_2026.reconstructed.summary.trade_count,
          forward_trades:ledger.forward?.summary?.trade_count||ledger.summary.trade_count,
          annual_trades:ledger.annual_2026.trades.length,
          last_forward_event:ledger.summary.last_event
        };
        payload={...payload,source_payload:source};
        canonicalLedgerSource=true;
      }catch(e){
        canonicalLedgerError=String(e?.message||e);
      }
    }

    res.setHeader('Cache-Control','no-store');
    return res.status(200).json({
      ...x,
      payload,
      effective_stale:tradeStale,
      trade_effective_stale:tradeStale,
      display_effective_stale:displayStale,
      canonical_ledger_source:canonicalLedgerSource,
      canonical_ledger_error:canonicalLedgerError,
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
}
"""
    p.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.26" not in text:
            raise SystemExit(f"v7.4.26 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.26", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")

    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    for marker in (
        "_r5CanonicalLedger",
        "R5_1_RECONSTRUCTED_2026",
        "R5_1_CANONICAL_FORWARD_LOG",
        "strategy_ledger",
        "canonical_ledger_source",
        "r5_ledger_read_model",
        "annual_2026",
        "trade_gate_unchanged:true",
    ):
        if marker not in assets:
            raise SystemExit(f"canonical ledger API missing {marker}")

    for marker in (
        "r5_shadow_ledger",
        "R5.1 2026 Annual Ledger",
        "2026 전체 Ledger",
        "loadUsPrimaryChart",
        "tradeSnapshotValidity",
        "Execution Quality:",
    ):
        if marker not in app:
            raise SystemExit(f"preserved UI missing {marker}")

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
        "r5_canonical_ledger_source": "strategy_ledger",
        "r5_snapshot_ledger_dependency_removed": True,
        "ledger_augmentation_soft_fail": True,
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.26",
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7427-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_api(src)
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
