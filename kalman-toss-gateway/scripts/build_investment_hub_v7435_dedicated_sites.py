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
ASSET_ROOT = ROOT / "kalman-toss-gateway/web/market-sites"
OUT_ROOT = ROOT / "kalman-hub-recovery/v7.4.35"
TARGET = "vNext.7.4.35"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.34 base manifest was not generated")


def decode_manifest(manifest: Path, out: Path) -> None:
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(rows) != 30:
        raise SystemExit(f"expected 30 base files, got {len(rows)}")
    for row in rows:
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe path: {rel}")
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(base64.b64decode(row["data_b64"]))


def overlay_frontend(src: Path, market: str) -> None:
    root = ASSET_ROOT / market.lower()
    if not root.is_dir():
        raise SystemExit(f"missing frontend asset root: {root}")
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel = p.relative_to(root)
        dst = src / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)


def patch_health(src: Path) -> None:
    p = src / "api/health.js"
    text = p.read_text(encoding="utf-8")
    if "vNext.7.4.34" not in text:
        raise SystemExit("v7.4.34 health anchor missing")
    p.write_text(text.replace("vNext.7.4.34", TARGET), encoding="utf-8")


def validate_common(src: Path, market: str) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"{market}: API count changed: {len(api)}")
    health = (src / "api/health.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    index = (src / "index.html").read_text(encoding="utf-8")
    if TARGET not in health:
        raise SystemExit(f"{market}: target health version missing")
    for marker in ("trade_enabled:false", "account_trade_execution:false"):
        if marker not in health:
            raise SystemExit(f"{market}: read-only invariant missing: {marker}")
    for marker in (
        "NEON_STRATEGY_SIGNAL",
        "NEON_SHADOW_PORTFOLIO_SNAPSHOT",
        "augmentAssetsSelectorsFromNeon",
        "canonical_ledger_source",
    ):
        if marker not in assets:
            raise SystemExit(f"{market}: preserved API marker missing: {marker}")
    for url in (
        "https://kalman-investment-hub-v2.vercel.app",
        "https://kalman-investment-hub-kr.vercel.app",
        "https://kalman-investment-hub-us.vercel.app",
    ):
        frontend = "\n".join(
            p.read_text(encoding="utf-8")
            for p in src.glob("*.js")
            if p.is_file()
        )
        if url not in frontend:
            raise SystemExit(f"{market}: navigation URL missing: {url}")
    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)
    return {
        "market": market,
        "version": TARGET,
        "base_version": "vNext.7.4.34",
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "canonical_r5_ledger_preserved": True,
        "shadow_neon_read_model_preserved": True,
    }


def validate_market(src: Path, market: str) -> dict:
    report = validate_common(src, market)
    index = (src / "index.html").read_text(encoding="utf-8")
    if market == "KR":
        core = (src / "core.js").read_text(encoding="utf-8")
        compact = (src / "compact.js").read_text(encoding="utf-8")
        chart = (src / "chart.js").read_text(encoding="utf-8")
        for marker in ("Kalman · KR Investment Hub",):
            if marker not in index:
                raise SystemExit(f"KR index marker missing: {marker}")
        for marker in ('siteNav("KR")', "현재 OPEN", "오늘 Signal", "KR Universe"):
            if marker not in compact:
                raise SystemExit(f"KR compact marker missing: {marker}")
        for marker in ("STRICT vs BUFFER", "strategyCompareHtml", "universeHtml"):
            if marker not in core:
                raise SystemExit(f"KR core marker missing: {marker}")
        if "function draw(" not in chart:
            raise SystemExit("KR chart renderer missing")
        report.update({
            "kr_top3_cycle_preserved": True,
            "kr_strategy_compare_preserved": True,
            "kr_interactive_chart_preserved": True,
        })
    elif market == "US":
        app = (src / "app.js").read_text(encoding="utf-8")
        if "Kalman · US Investment Hub" not in index:
            raise SystemExit("US index marker missing")
        for marker in (
            "siteNav('US')",
            "Research Benchmark · TOP-1 vs TOP-6",
            "R5.1 2026 Ledger",
            "FORWARD SHADOW",
            "/api/assets?view=control",
            "RECONSTRUCTED · 2026",
            "US SESSION · KST END DATE",
            "NEXT HOURLY CYCLE",
            "ACTION · BUY / SELL",
            "5M EXECUTION WATCHER",
            "EXPECTED WEB UPDATE",
            "sessionStatusHtml",
        ):
            if marker not in app:
                raise SystemExit(f"US app marker missing: {marker}")
        null_guard = "x===null||x===undefined||x===''?null"
        if null_guard not in app:
            raise SystemExit("US null return guard missing")
        report.update({
            "us_research_benchmark_visible": True,
            "us_annual_ledger_visible": True,
            "us_forward_shadow_visible": True,
            "open_return_null_semantics_preserved": True,
        })
    else:
        raise SystemExit(f"unsupported market: {market}")
    return report


def emit_source_manifest(src: Path, out: Path) -> None:
    rows = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rows.append(json.dumps({
            "file": p.relative_to(src).as_posix(),
            "data_b64": base64.b64encode(p.read_bytes()).decode("ascii"),
        }, separators=(",", ":"), ensure_ascii=False))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_market(market: str) -> dict:
    out_dir = OUT_ROOT / market.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"kalman-v7435-{market.lower()}-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        overlay_frontend(src, market)
        patch_health(src)
        report = validate_market(src, market)
        manifest = out_dir / "source_manifest.ndjson"
        emit_source_manifest(src, manifest)
        report["source_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (out_dir / "build_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report


def main() -> int:
    build_base()
    reports = [build_market("KR"), build_market("US")]
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
