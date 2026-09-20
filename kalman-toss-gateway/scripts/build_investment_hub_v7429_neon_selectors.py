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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7428_r5_null_fix.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.28/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.29"
TARGET = "vNext.7.4.29"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.28 base manifest was not generated")


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
    anchor = "module.exports=async(req,res)=>{"
    if anchor not in text:
        raise SystemExit("assets module anchor missing")

    helper = r"""
async function augmentAssetsSelectorsFromNeon(basePayload){
  const legacySelectorSource=basePayload?.selector_source||'NONE';
  const legacyKrSelectorSource=basePayload?.kr_selector_source||'NONE';
  if(!process.env.DATABASE_URL_READER){
    return {
      ...basePayload,
      selector_read_model:{source:'LEGACY_CACHE',canonical:false,error:'DB_NOT_CONFIGURED',legacy_source:legacySelectorSource},
      kr_selector_read_model:{source:'LEGACY_CACHE',canonical:false,error:'DB_NOT_CONFIGURED',legacy_source:legacyKrSelectorSource}
    };
  }
  try{
    const {neon}=await import('@neondatabase/serverless');
    const sql=neon(process.env.DATABASE_URL_READER);
    const rows=await sql`
      SELECT market,run_id,generated_at,data_as_of,stale_after,status,payload
      FROM v_latest_dashboard_snapshot
      WHERE market IN ('US','KR')
    `;
    const byMarket=Object.fromEntries((rows||[]).map(x=>[String(x.market||'').toUpperCase(),x]));
    let out={...basePayload};

    const us=byMarket.US;
    const usSource=us?.payload?.source_payload;
    if(us&&us.status==='READY'&&usSource&&typeof usSource==='object'&&usSource.today_selector){
      const staleAt=Date.parse(us.stale_after||'');
      const effectiveStale=!Number.isFinite(staleAt)||Date.now()>staleAt;
      out={
        ...out,
        legacy_selector_source:legacySelectorSource,
        selector_source:'NEON_DASHBOARD_SNAPSHOT',
        today_selector:{
          ...usSource.today_selector,
          stale:effectiveStale,
          ingested_at_utc:usSource.generated_at_utc||us.generated_at||null,
          snapshot_run_id:us.run_id||null,
          snapshot_data_as_of:us.data_as_of||null
        },
        model_universe:usSource.model_universe||null,
        model_as_of_utc:usSource.model_as_of_utc||usSource.today_selector.as_of_utc||us.data_as_of||null,
        selector_read_model:{
          source:'NEON_DASHBOARD_SNAPSHOT',
          canonical:true,
          legacy_source:legacySelectorSource,
          run_id:us.run_id||null,
          generated_at:us.generated_at||null,
          data_as_of:us.data_as_of||null,
          stale_after:us.stale_after||null,
          effective_stale:effectiveStale
        }
      };
    }else{
      out.selector_read_model={
        source:'LEGACY_CACHE',
        canonical:false,
        legacy_source:legacySelectorSource,
        error:'US_CANONICAL_SELECTOR_UNAVAILABLE'
      };
    }

    const kr=byMarket.KR;
    const krSource=kr?.payload?.source_payload;
    if(kr&&kr.status==='READY'&&krSource&&typeof krSource==='object'){
      const staleAt=Date.parse(kr.stale_after||'');
      const runtimeStale=!Number.isFinite(staleAt)||Date.now()>staleAt;
      const sourceStale=Boolean(krSource?.freshness?.stale ?? krSource?.source_stale ?? krSource?.stale);
      const effectiveStale=sourceStale||runtimeStale;
      out={
        ...out,
        legacy_kr_selector_source:legacyKrSelectorSource,
        kr_selector_source:'NEON_DASHBOARD_SNAPSHOT',
        kr_selector:{
          ...krSource,
          stale:effectiveStale,
          source_stale:sourceStale,
          cache_stale:false,
          runtime_stale:runtimeStale,
          effective_stale:effectiveStale,
          stale_semantics:'NEON_SOURCE_OR_RUNTIME_FRESHNESS',
          actionability:effectiveStale?'WAIT_STALE':(krSource.actionability||'RESEARCH_LIVE'),
          snapshot_run_id:kr.run_id||null,
          snapshot_data_as_of:kr.data_as_of||null
        },
        kr_selector_read_model:{
          source:'NEON_DASHBOARD_SNAPSHOT',
          canonical:true,
          legacy_source:legacyKrSelectorSource,
          run_id:kr.run_id||null,
          generated_at:kr.generated_at||null,
          data_as_of:kr.data_as_of||null,
          stale_after:kr.stale_after||null,
          source_stale:sourceStale,
          runtime_stale:runtimeStale,
          effective_stale:effectiveStale
        }
      };
    }else{
      out.kr_selector_read_model={
        source:'LEGACY_CACHE',
        canonical:false,
        legacy_source:legacyKrSelectorSource,
        error:'KR_CANONICAL_SELECTOR_UNAVAILABLE'
      };
    }
    return out;
  }catch(e){
    const detail=String(e?.message||e);
    return {
      ...basePayload,
      selector_read_model:{source:'LEGACY_CACHE',canonical:false,error:detail,legacy_source:legacySelectorSource},
      kr_selector_read_model:{source:'LEGACY_CACHE',canonical:false,error:detail,legacy_source:legacyKrSelectorSource}
    };
  }
}

"""
    text = text.replace(anchor, helper + anchor, 1)

    old = "try{const payload=await buildAssetsPayload();res.setHeader('Cache-Control','no-store');return res.status(200).json(payload);}catch(e){return res.status(500).json({error:'ASSETS_BUILD_FAILED',detail:String(e?.message||e)});}"
    new = "try{const basePayload=await buildAssetsPayload();const payload=await augmentAssetsSelectorsFromNeon(basePayload);res.setHeader('Cache-Control','no-store');return res.status(200).json(payload);}catch(e){return res.status(500).json({error:'ASSETS_BUILD_FAILED',detail:String(e?.message||e)});}"
    if old not in text:
        raise SystemExit("assets default response anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.28" not in text:
            raise SystemExit(f"v7.4.28 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.28", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api_files = sorted((src / "api").rglob("*.js"))
    if len(api_files) != 12:
        raise SystemExit(f"API count changed: {len(api_files)}")

    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    for marker in (
        "augmentAssetsSelectorsFromNeon",
        "NEON_DASHBOARD_SNAPSHOT",
        "selector_read_model",
        "kr_selector_read_model",
        "legacy_selector_source",
        "legacy_kr_selector_source",
        "v_latest_dashboard_snapshot",
    ):
        if marker not in assets:
            raise SystemExit(f"selector read-model marker missing {marker}")

    for marker in (
        "_r5CanonicalLedger",
        "canonical_ledger_source",
        "R5_1_RECONSTRUCTED_2026",
        "R5_1_CANONICAL_FORWARD_LOG",
        "if(v==null||v==='')return null;",
    ):
        if marker not in assets:
            raise SystemExit(f"preserved R5 marker missing {marker}")

    for marker in ("R5.1 2026 Annual Ledger", "Execution Quality:", "tradeSnapshotValidity"):
        if marker not in app:
            raise SystemExit(f"preserved UI marker missing {marker}")

    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("web read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "us_selector_source": "NEON_DASHBOARD_SNAPSHOT",
        "kr_selector_source": "NEON_DASHBOARD_SNAPSHOT",
        "legacy_cache_fallback": True,
        "canonical_r5_ledger_preserved": True,
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.28",
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7429-") as td:
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
