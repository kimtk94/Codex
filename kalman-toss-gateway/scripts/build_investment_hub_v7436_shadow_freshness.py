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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7434_market_sites.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.34/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.36"
TARGET = "vNext.7.4.36"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.34 base manifest was not generated")


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


def patch_shadow_freshness(src: Path) -> None:
    p = src / "api/assets.js"
    text = p.read_text(encoding="utf-8")

    anchor = """    try{
      if(!process.env.DATABASE_URL_READER)throw new Error('DB_NOT_CONFIGURED');"""
    helper = """    const freshnessThresholdHours={US:96,KR:96,BTC:36};
    function ageHours(value){
      const ts=Date.parse(value||'');
      if(!Number.isFinite(ts))return null;
      return Math.max(0,(Date.now()-ts)/3600000);
    }
    function freshnessState(asOfMap){
      const ages={},stale=[];
      for(const market of ['US','KR','BTC']){
        const age=ageHours(asOfMap&&asOfMap[market]);
        ages[market]=age==null?null:Number(age.toFixed(3));
        if(age==null||age>freshnessThresholdHours[market])stale.push(market);
      }
      return {ages,stale};
    }

"""
    if anchor not in text:
        raise SystemExit("SHADOW helper anchor missing")
    text = text.replace(anchor, helper + anchor, 1)

    old = """      const rankingPayload=portfolio&&portfolio.payload||legacy||null;
      const rankingSource=portfolio?'NEON_SHADOW_PORTFOLIO_SNAPSHOT':(legacy?'LEGACY_STANDALONE_BAKEOFF':'UNAVAILABLE');
      const rankingAsOf=portfolio&&portfolio.as_of||legacy&&legacy.latest_as_of||null;
      const rankingUpdatedAt=portfolio&&portfolio.updated_at||legacy&&legacy.updated_at||null;
      const rankingStale=Boolean(!rankingAsOf||!latestAsOf||Date.parse(rankingAsOf)<Date.parse(latestAsOf));
      res.setHeader('X-Kalman-Shadow-Source','neon-strategy-signal');"""
    new = """      const signalFreshness=freshnessState({
        US:signals.US&&signals.US.as_of,
        KR:signals.KR&&signals.KR.as_of,
        BTC:signals.BTC&&signals.BTC.as_of
      });
      const rankingPayload=portfolio&&portfolio.payload||legacy||null;
      const rankingSource=portfolio?'NEON_SHADOW_PORTFOLIO_SNAPSHOT':(legacy?'LEGACY_STANDALONE_BAKEOFF':'UNAVAILABLE');
      const rankingAsOf=portfolio&&portfolio.as_of||legacy&&legacy.latest_as_of||null;
      const rankingUpdatedAt=portfolio&&portfolio.updated_at||legacy&&legacy.updated_at||null;
      const rankingMarketDataAsOf=rankingPayload&&rankingPayload.market_data_as_of||{};
      const rankingFreshness=freshnessState(rankingMarketDataAsOf);
      const rankingRelativeStale=Boolean(!rankingAsOf||!latestAsOf||Date.parse(rankingAsOf)<Date.parse(latestAsOf));
      const rankingStale=Boolean(
        rankingSource!=='NEON_SHADOW_PORTFOLIO_SNAPSHOT'||
        rankingRelativeStale||
        rankingFreshness.stale.length
      );
      const signalSourceFresh=signalFreshness.stale.length===0;
      const dataFreshnessStatus=signalSourceFresh&&!rankingStale?'FRESH':'STALE';
      res.setHeader('X-Kalman-Shadow-Source','neon-strategy-signal');"""
    if old not in text:
        raise SystemExit("SHADOW ranking freshness anchor missing")
    text = text.replace(old, new, 1)

    old_response = """        experiment:'NEON_FORWARD_SHADOW_READ_MODEL',signal_source:'NEON_STRATEGY_SIGNAL',
        signal_source_fresh:true,latest_as_of:latestAsOf,updated_at:updatedAt,signals,
        ranking_source:rankingSource,
        ranking_as_of:rankingAsOf,ranking_updated_at:rankingUpdatedAt,ranking_stale:rankingStale,
        ranking_error:portfolioError||legacyError,"""
    new_response = """        experiment:'NEON_FORWARD_SHADOW_READ_MODEL',signal_source:'NEON_STRATEGY_SIGNAL',
        signal_source_fresh:signalSourceFresh,signal_stale_markets:signalFreshness.stale,
        signal_age_hours:signalFreshness.ages,freshness_threshold_hours:freshnessThresholdHours,
        data_freshness_status:dataFreshnessStatus,
        latest_as_of:latestAsOf,updated_at:updatedAt,signals,
        ranking_source:rankingSource,
        ranking_as_of:rankingAsOf,ranking_updated_at:rankingUpdatedAt,ranking_stale:rankingStale,
        ranking_relative_stale:rankingRelativeStale,ranking_market_data_as_of:rankingMarketDataAsOf,
        ranking_stale_markets:rankingFreshness.stale,ranking_age_hours:rankingFreshness.ages,
        ranking_error:portfolioError||legacyError,"""
    if old_response not in text:
        raise SystemExit("SHADOW response anchor missing")
    text = text.replace(old_response, new_response, 1)

    old_fallback = """          signal_source:'LEGACY_STANDALONE_BAKEOFF',signal_source_fresh:false,
          signal_source_error:String(err?.message||err),ranking_source:'LEGACY_STANDALONE_BAKEOFF',
          ranking_as_of:legacy.latest_as_of||null,ranking_updated_at:legacy.updated_at||null,ranking_stale:true,"""
    new_fallback = """          signal_source:'LEGACY_STANDALONE_BAKEOFF',signal_source_fresh:false,
          signal_stale_markets:['US','KR','BTC'],signal_age_hours:{US:null,KR:null,BTC:null},
          freshness_threshold_hours:freshnessThresholdHours,data_freshness_status:'STALE',
          signal_source_error:String(err?.message||err),ranking_source:'LEGACY_STANDALONE_BAKEOFF',
          ranking_as_of:legacy.latest_as_of||null,ranking_updated_at:legacy.updated_at||null,ranking_stale:true,
          ranking_relative_stale:true,ranking_stale_markets:['US','KR','BTC'],
          ranking_age_hours:{US:null,KR:null,BTC:null},"""
    if old_fallback not in text:
        raise SystemExit("SHADOW fallback anchor missing")
    text = text.replace(old_fallback, new_fallback, 1)
    p.write_text(text, encoding="utf-8")


def patch_shadow_ui(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")
    old = """  const signalBadge=signalSource==='NEON_STRATEGY_SIGNAL'?badge('Neon Signal','ok'):badge('Legacy Signal','warn');"""
    new = """  const signalBadge=signalSource==='NEON_STRATEGY_SIGNAL'?(j.signal_source_fresh?badge('Neon Signal','ok'):badge('Signal stale','warn')):badge('Legacy Signal','warn');"""
    if old not in text:
        raise SystemExit("renderShadow signal badge anchor missing")
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.34" not in text:
            raise SystemExit(f"v7.4.34 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.34", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api_files = sorted((src / "api").rglob("*.js"))
    if len(api_files) != 12:
        raise SystemExit(f"API count changed: {len(api_files)}")

    api = (src / "api/assets.js").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")
    index = (src / "index.html").read_text(encoding="utf-8")
    payload = (src / "lib/assets-payload.js").read_text(encoding="utf-8")

    for marker in (
        "freshnessThresholdHours={US:96,KR:96,BTC:36}",
        "signal_stale_markets",
        "signal_age_hours",
        "ranking_stale_markets",
        "ranking_age_hours",
        "ranking_market_data_as_of",
        "data_freshness_status",
        "NEON_SHADOW_PORTFOLIO_SNAPSHOT",
        "NEON_STRATEGY_SIGNAL",
    ):
        if marker not in api:
            raise SystemExit(f"SHADOW freshness marker missing: {marker}")

    for marker in ("Signal stale", "Neon ranking"):
        if marker not in app:
            raise SystemExit(f"SHADOW UI marker missing: {marker}")

    for marker in ("augmentAssetsSelectorsFromNeon", "_r5CanonicalLedger", "canonical_ledger_source"):
        if marker not in api:
            raise SystemExit(f"preserved API marker missing: {marker}")
    if "overlayStaleEtfDisplayPrices" not in payload:
        raise SystemExit("ETF display overlay marker missing")

    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "base_version": "vNext.7.4.34",
        "shadow_wall_clock_freshness": True,
        "freshness_threshold_hours": {"US": 96, "KR": 96, "BTC": 36},
        "updated_at_not_used_as_data_freshness": True,
        "canonical_r5_ledger_preserved": True,
        "etf_display_overlay_preserved": True,
        "trade_gate_unchanged": True,
        "web_read_only": True,
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7436-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_shadow_freshness(src)
        patch_shadow_ui(src)
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
