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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7424_execution_telemetry.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.24/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.25"
TARGET = "vNext.7.4.25"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.24 base manifest was not generated")


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


def patch_app(src: Path) -> None:
    p = src / "app.js"
    text = p.read_text(encoding="utf-8")

    copy_anchor = """    '<div class="small"><b>연구용 벤치마크:</b> -3% 손절, +20% 익절, 모델 교체를 포함하지 않습니다. 실매매 손익과 직접 비교하지 않습니다. 구간이 서로 겹치므로 연속 복리값은 포트폴리오 누적수익으로 표시하지 않습니다.</div>';
  renderExecutionLedger(ctl);"""
    copy_replacement = """    '<div class="small"><b>연구용 벤치마크:</b> -3% 손절, +20% 익절, 모델 교체를 포함하지 않습니다. 실매매 손익과 직접 비교하지 않습니다. 구간이 서로 겹치므로 연속 복리값은 포트폴리오 누적수익으로 표시하지 않습니다.</div>';
  var universeBox=$('#universeBenchmark');
  if(universeBox){
    universeBox.className='';
    universeBox.innerHTML=box.innerHTML;
  }
  renderExecutionLedger(ctl);"""
    if copy_anchor not in text:
        raise SystemExit("benchmark render anchor missing")
    text = text.replace(copy_anchor, copy_replacement, 1)

    controls_anchor = """      '<section class="card universe-controls section">'+"""
    benchmark_card = """      '<section class="card section universe-benchmark-card">'+
        '<div class="section-title"><div><h3>연구 벤치마크 · TOP-1 vs TOP-6</h3><span class="small">4-bucket 연구 비교 · 실매매 성과와 분리</span></div><span class="pill">RESEARCH</span></div>'+
        '<div id="universeBenchmark" class="muted">연구 벤치마크를 불러오는 중...</div>'+
      '</section>'+
      '<section class="card universe-controls section">'+"""
    if controls_anchor not in text:
        raise SystemExit("universe controls anchor missing")
    text = text.replace(controls_anchor, benchmark_card, 1)

    rerender_anchor = """  renderUniverseTable();
}
async function loadUniverse(){"""
    rerender_replacement = """  renderUniverseTable();
  if(kalmanCommandState.control)renderBenchmark(kalmanCommandState.control);
}
async function loadUniverse(){"""
    if rerender_anchor not in text:
        raise SystemExit("universe rerender anchor missing")
    text = text.replace(rerender_anchor, rerender_replacement, 1)

    p.write_text(text, encoding="utf-8")


def patch_style(src: Path) -> None:
    p = src / "style.css"
    text = p.read_text(encoding="utf-8")
    addition = """
/* vNext.7.4.25 — persistent research benchmark */
.universe-benchmark-card{border-color:#30415f;background:linear-gradient(180deg,#101a2e,#0c1526)}
.universe-benchmark-card .benchmark-grid{margin-top:0}
.universe-benchmark-card .benchmark-foot{padding-bottom:7px}
@media(max-width:600px){.universe-benchmark-card .section-title{align-items:flex-start}}
"""
    if "vNext.7.4.25 — persistent research benchmark" not in text:
        text += addition
    p.write_text(text, encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.24" not in text:
            raise SystemExit(f"v7.4.24 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.24", TARGET), encoding="utf-8")


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
        "universeBenchmark",
        "연구 벤치마크 · TOP-1 vs TOP-6",
        "if(kalmanCommandState.control)renderBenchmark(kalmanCommandState.control)",
        "Execution Quality:",
    ):
        if marker not in app:
            raise SystemExit(f"app missing {marker}")

    if ".universe-mode .command-shell,.universe-mode .account{display:none}" not in style:
        raise SystemExit("Universe focus CSS changed unexpectedly")
    if "universe-benchmark-card" not in style:
        raise SystemExit("persistent benchmark CSS missing")

    for marker in ("net_return", "round_trip_cost_bps", "entry_fill_latency_ms"):
        if marker not in assets:
            raise SystemExit(f"execution telemetry missing {marker}")

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
        "persistent_universe_benchmark": True,
        "direct_universe_race_guard": True,
        "execution_quality_ui": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.24",
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7425-") as td:
        src = Path(td) / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
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
