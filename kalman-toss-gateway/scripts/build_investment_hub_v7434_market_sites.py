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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7433_shadow_ranking_neon.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.33/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.34"
TARGET = "vNext.7.4.34"
KR_URL = "https://kalman-investment-hub-kr.vercel.app"
US_URL = "https://kalman-investment-hub-us.vercel.app"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.33 base manifest was not generated")


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


def patch_index(src: Path) -> None:
    p = src / "index.html"
    text = p.read_text(encoding="utf-8")
    anchor = """    </header>

    <section class="command-shell section">"""
    block = """    </header>

    <section class="market-sites section" aria-label="독립 시장 사이트">
      <a class="market-site-link market-site-kr" href="https://kalman-investment-hub-kr.vercel.app" target="_blank" rel="noopener noreferrer">
        <span class="market-site-code">KR</span>
        <span class="market-site-copy"><strong>한국장 전용 사이트</strong><small>KR Investment Hub · 별도 화면에서 열기</small></span>
        <span class="market-site-open" aria-hidden="true">↗</span>
      </a>
      <a class="market-site-link market-site-us" href="https://kalman-investment-hub-us.vercel.app" target="_blank" rel="noopener noreferrer">
        <span class="market-site-code">US</span>
        <span class="market-site-copy"><strong>미국장 전용 사이트</strong><small>US Investment Hub · 별도 화면에서 열기</small></span>
        <span class="market-site-open" aria-hidden="true">↗</span>
      </a>
    </section>

    <section class="command-shell section">"""
    if "market-sites section" not in text:
        if anchor not in text:
            raise SystemExit("header/command-shell anchor missing")
        text = text.replace(anchor, block, 1)
    if "vNext.7.4.33" not in text:
        raise SystemExit("v7.4.33 version anchor missing in index.html")
    p.write_text(text.replace("vNext.7.4.33", TARGET), encoding="utf-8")


def patch_style(src: Path) -> None:
    p = src / "style.css"
    text = p.read_text(encoding="utf-8")
    addition = """
/* vNext.7.4.34 — dedicated KR / US site links */
.market-sites{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.market-site-link{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:14px 16px;border:1px solid rgba(148,163,184,.28);border-radius:14px;background:rgba(15,23,42,.55);color:inherit;text-decoration:none;transition:transform .15s ease,border-color .15s ease,background .15s ease}
.market-site-link:hover{transform:translateY(-1px);border-color:rgba(148,163,184,.52);background:rgba(30,41,59,.72)}
.market-site-code{display:grid;place-items:center;min-width:42px;height:32px;padding:0 8px;border-radius:9px;font-size:12px;font-weight:800;letter-spacing:.08em;border:1px solid rgba(148,163,184,.3)}
.market-site-copy{display:flex;min-width:0;flex-direction:column;gap:3px}
.market-site-copy strong{font-size:14px}
.market-site-copy small{font-size:12px;opacity:.72;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.market-site-open{font-size:18px;opacity:.65}
.market-site-kr .market-site-code{background:rgba(37,99,235,.14)}
.market-site-us .market-site-code{background:rgba(220,38,38,.12)}
@media(max-width:760px){.market-sites{grid-template-columns:1fr}.market-site-link{padding:12px 14px}}
"""
    if "vNext.7.4.34 — dedicated KR / US site links" not in text:
        text += addition
    p.write_text(text, encoding="utf-8")


def patch_health(src: Path) -> None:
    p = src / "api/health.js"
    text = p.read_text(encoding="utf-8")
    if "vNext.7.4.33" not in text:
        raise SystemExit("v7.4.33 version anchor missing in api/health.js")
    p.write_text(text.replace("vNext.7.4.33", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")

    index = (src / "index.html").read_text(encoding="utf-8")
    style = (src / "style.css").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")

    for marker in ("market-sites section", "한국장 전용 사이트", "미국장 전용 사이트", KR_URL, US_URL):
        if marker not in index:
            raise SystemExit(f"market site marker missing: {marker}")
    for marker in (".market-sites", ".market-site-link", ".market-site-kr", ".market-site-us"):
        if marker not in style:
            raise SystemExit(f"market site CSS missing: {marker}")
    for marker in ("universeBenchmark", "연구 벤치마크 · TOP-1 vs TOP-6", "function renderCommandAccount(", "function renderCommandModel(", "Neon ranking"):
        if marker not in app:
            raise SystemExit(f"preserved UI marker missing: {marker}")
    for marker in ("NEON_STRATEGY_SIGNAL", "NEON_SHADOW_PORTFOLIO_SNAPSHOT", "augmentAssetsSelectorsFromNeon", "canonical_ledger_source"):
        if marker not in assets:
            raise SystemExit(f"preserved API marker missing: {marker}")
    if TARGET not in index or TARGET not in health:
        raise SystemExit("version marker missing")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        raise SystemExit("read-only invariant missing")

    if shutil.which("node"):
        for q in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(q)], check=True, stdout=subprocess.DEVNULL)

    return {
        "version": TARGET,
        "base_version": "vNext.7.4.33",
        "kr_site_url": KR_URL,
        "us_site_url": US_URL,
        "dedicated_market_site_links": True,
        "shadow_neon_read_model_preserved": True,
        "canonical_r5_ledger_preserved": True,
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7434-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        patch_index(src)
        patch_style(src)
        patch_health(src)
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
