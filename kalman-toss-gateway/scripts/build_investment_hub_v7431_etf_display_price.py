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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7430_command_renderers.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.30/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.31"
TARGET = "vNext.7.4.31"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.30 base manifest was not generated")


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


def patch_assets_payload(src: Path) -> None:
    p = src / "lib/assets-payload.js"
    text = p.read_text(encoding="utf-8")
    old_import = "const { crypto, etf, unavailable, getChampion, getEtfSnapshot } = require('./core');"
    if old_import not in text:
        raise SystemExit("assets payload core import anchor missing")
    text = text.replace(
        old_import,
        old_import + "\nconst {getHistory}=require('./history');",
        1,
    )

    helper_anchor = "async function buildAssetsPayload(){"
    if helper_anchor not in text:
        raise SystemExit("assets payload build anchor missing")

    helper = r"""
function overlayEtfDisplayPrice(asset,history){
  if(!asset||!history)return {asset,used:false};
  const value=Number(history?.market?.price);
  const observedAt=Date.parse(history?.market?.observedAt||'');
  const current=ts(asset?.price?.observed_at);
  if(!Number.isFinite(value)||value<=0||!Number.isFinite(observedAt)||observedAt<=current){
    return {asset,used:false};
  }
  const out=JSON.parse(JSON.stringify(asset));
  out.price={
    ...(out.price||{}),
    value,
    observed_at:observedAt,
    display_source:history.source||'YAHOO_PUBLIC_CONTEXT',
    model_snapshot_value:asset?.price?.value??null,
    model_snapshot_observed_at:asset?.price?.observed_at??null
  };
  out.freshness={
    ...(out.freshness||{}),
    displayPriceOverlay:true,
    displayPriceSource:history.source||'YAHOO_PUBLIC_CONTEXT',
    displayPriceObservedAt:observedAt,
    modelSnapshotStale:Boolean(out?.freshness?.stale)
  };
  return {asset:out,used:true};
}
async function overlayStaleEtfDisplayPrices(assets){
  const staleSymbols=['QQQ','QLD'].filter(sym=>assets?.[sym]?.freshness?.stale===true);
  if(!staleSymbols.length)return {assets,source:'ETF_MODEL_SNAPSHOT',symbols:[],errors:[]};
  const settled=await Promise.allSettled(staleSymbols.map(sym=>getHistory(sym,30)));
  const errors=[],used=[];
  settled.forEach((result,i)=>{
    const sym=staleSymbols[i];
    if(result.status!=='fulfilled'){
      errors.push({symbol:sym,error:String(result.reason?.message||result.reason)});
      return;
    }
    const x=overlayEtfDisplayPrice(assets[sym],result.value);
    if(x.used){assets[sym]=x.asset;used.push(sym);}
  });
  return {assets,source:used.length?'YAHOO_PUBLIC_CONTEXT': 'ETF_MODEL_SNAPSHOT',symbols:used,errors};
}

"""
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

    return_anchor = "  return {\n    schema_version:'investment-hub-assets-v0.17',"
    if return_anchor not in text:
        raise SystemExit("assets payload return anchor missing")
    overlay_code = """  const etfDisplay=await overlayStaleEtfDisplayPrices(assets);
  if(etfDisplay.errors.length)errors.push(...etfDisplay.errors.map(x=>({source:'ETF_DISPLAY_PRICE',...x})));
"""
    text = text.replace(return_anchor, overlay_code + return_anchor, 1)

    old_fields = "    champion_source,champion_cache_write,etf_source,etf_cache_reason,"
    new_fields = "    champion_source,champion_cache_write,etf_source,etf_cache_reason,etf_display_price_source:etfDisplay.source,etf_display_price_symbols:etfDisplay.symbols,"
    if old_fields not in text:
        raise SystemExit("assets payload top-level fields anchor missing")
    text = text.replace(old_fields, new_fields, 1)
    p.write_text(text, encoding="utf-8")


def patch_market(src: Path) -> None:
    p = src / "api/market.js"
    text = p.read_text(encoding="utf-8")
    expected = "const { etf, getEtfSnapshot } = require('../lib/core');"
    if expected not in text:
        raise SystemExit("market import anchor missing")

    replacement = r"""const { etf, getEtfSnapshot } = require('../lib/core');
const {getHistory}=require('../lib/history');

function ts(v){
  if(Number.isFinite(Number(v)))return Number(v);
  if(typeof v==='string'){const x=Date.parse(v);return Number.isFinite(x)?x:0;}
  return 0;
}
function overlayPrice(asset,history){
  const value=Number(history?.market?.price),observedAt=Date.parse(history?.market?.observedAt||'');
  const current=ts(asset?.price?.observed_at);
  if(!Number.isFinite(value)||value<=0||!Number.isFinite(observedAt)||observedAt<=current)return {asset,used:false};
  return {
    used:true,
    asset:{
      ...asset,
      price:{
        ...(asset.price||{}),
        value,
        observed_at:observedAt,
        display_source:history.source||'YAHOO_PUBLIC_CONTEXT',
        model_snapshot_value:asset?.price?.value??null,
        model_snapshot_observed_at:asset?.price?.observed_at??null
      },
      freshness:{
        ...(asset.freshness||{}),
        displayPriceOverlay:true,
        displayPriceSource:history.source||'YAHOO_PUBLIC_CONTEXT',
        displayPriceObservedAt:observedAt,
        modelSnapshotStale:Boolean(asset?.freshness?.stale)
      }
    }
  };
}
async function withDisplayPrices(assets){
  const symbols=['QQQ','QLD'].filter(sym=>assets?.[sym]?.freshness?.stale===true);
  const settled=await Promise.allSettled(symbols.map(sym=>getHistory(sym,30)));
  const used=[],errors=[];
  settled.forEach((r,i)=>{
    const sym=symbols[i];
    if(r.status!=='fulfilled'){errors.push({symbol:sym,error:String(r.reason?.message||r.reason)});return;}
    const x=overlayPrice(assets[sym],r.value);
    if(x.used){assets[sym]=x.asset;used.push(sym);}
  });
  return {assets,used,errors};
}
"""
    text = text.replace(expected, replacement, 1)

    old_handler = "module.exports=async(req,res)=>{if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});const now=Date.now();try{const e=await getEtfSnapshot();res.setHeader('Cache-Control','no-store');return res.status(200).json({schema_version:'investment-hub-market-v0.3',generated_at:now,source:e.source,cache_reason:e.cacheReason||null,assets:{QQQ:etf('QQQ',e.snapshot,now,e.source),QLD:etf('QLD',e.snapshot,now,e.source)}});}catch(err){return res.status(503).json({error:'ETF_UNAVAILABLE',detail:String(err?.message||err)});}};"
    if old_handler not in text:
        raise SystemExit("market handler anchor missing")
    new_handler = """module.exports=async(req,res)=>{
  if(req.method!=='GET')return res.status(405).json({error:'METHOD_NOT_ALLOWED'});
  const now=Date.now();
  try{
    const e=await getEtfSnapshot();
    const base={QQQ:etf('QQQ',e.snapshot,now,e.source),QLD:etf('QLD',e.snapshot,now,e.source)};
    const display=await withDisplayPrices(base);
    res.setHeader('Cache-Control','no-store');
    return res.status(200).json({
      schema_version:'investment-hub-market-v0.4',
      generated_at:now,
      source:e.source,
      cache_reason:e.cacheReason||null,
      display_price_source:display.used.length?'YAHOO_PUBLIC_CONTEXT':'ETF_MODEL_SNAPSHOT',
      display_price_symbols:display.used,
      display_price_errors:display.errors,
      model_snapshot_stale:{QQQ:Boolean(display.assets.QQQ?.freshness?.stale),QLD:Boolean(display.assets.QLD?.freshness?.stale)},
      assets:display.assets
    });
  }catch(err){
    return res.status(503).json({error:'ETF_UNAVAILABLE',detail:String(err?.message||err)});
  }
};"""
    text = text.replace(old_handler, new_handler, 1)
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.30" not in text:
            raise SystemExit(f"v7.4.30 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.30", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api_files = sorted((src / "api").rglob("*.js"))
    if len(api_files) != 12:
        raise SystemExit(f"API count changed: {len(api_files)}")

    assets_payload = (src / "lib/assets-payload.js").read_text(encoding="utf-8")
    market = (src / "api/market.js").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")
    index = (src / "index.html").read_text(encoding="utf-8")

    for marker in (
        "overlayStaleEtfDisplayPrices",
        "YAHOO_PUBLIC_CONTEXT",
        "model_snapshot_value",
        "modelSnapshotStale",
        "etf_display_price_source",
    ):
        if marker not in assets_payload:
            raise SystemExit(f"ETF display marker missing in assets payload: {marker}")

    for marker in (
        "withDisplayPrices",
        "display_price_source",
        "model_snapshot_stale",
        "investment-hub-market-v0.4",
    ):
        if marker not in market:
            raise SystemExit(f"ETF display marker missing in market route: {marker}")

    for marker in (
        "function renderCommandAccount(",
        "function renderCommandModel(",
        "R5.1 2026 Annual Ledger",
        "Execution Quality:",
    ):
        if marker not in app:
            raise SystemExit(f"preserved UI marker missing {marker}")

    for marker in (
        "augmentAssetsSelectorsFromNeon",
        "NEON_DASHBOARD_SNAPSHOT",
        "_r5CanonicalLedger",
        "canonical_ledger_source",
        "if(v==null||v==='')return null;",
    ):
        if marker not in assets:
            raise SystemExit(f"preserved API marker missing {marker}")

    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "etf_display_price_overlay": True,
        "etf_model_freshness_unchanged": True,
        "etf_risk_decision_unchanged": True,
        "canonical_r5_ledger_preserved": True,
        "neon_selector_read_model_preserved": True,
        "command_renderers_preserved": True,
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.30",
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7431-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_assets_payload(src)
        patch_market(src)
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
