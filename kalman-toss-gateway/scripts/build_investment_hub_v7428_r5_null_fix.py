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
BASE_BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7427_canonical_ledger.py"
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.27/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.28"
TARGET = "vNext.7.4.28"


def build_base() -> None:
    subprocess.run([sys.executable, str(BASE_BUILDER)], check=True)
    if not BASE_MANIFEST.is_file():
        raise SystemExit("v7.4.27 base manifest was not generated")


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
    old = """function _r5n(v){
  const x=Number(v);
  return Number.isFinite(x)?x:null;
}"""
    new = """function _r5n(v){
  if(v==null||v==='')return null;
  const x=Number(v);
  return Number.isFinite(x)?x:null;
}"""
    if old not in text:
        raise SystemExit("R5 numeric null anchor missing")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_versions(src: Path) -> None:
    for rel in ("index.html", "api/health.js"):
        p = src / rel
        text = p.read_text(encoding="utf-8")
        if "vNext.7.4.27" not in text:
            raise SystemExit(f"v7.4.27 version anchor missing in {rel}")
        p.write_text(text.replace("vNext.7.4.27", TARGET), encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API count changed: {len(api)}")
    index = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    assets = (src / "api/assets.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    if "if(v==null||v==='')return null;" not in assets:
        raise SystemExit("R5 null-preserving numeric conversion missing")
    for marker in (
        "_r5CanonicalLedger",
        "canonical_ledger_source",
        "R5_1_RECONSTRUCTED_2026",
        "R5_1_CANONICAL_FORWARD_LOG",
    ):
        if marker not in assets:
            raise SystemExit(f"canonical ledger marker missing {marker}")
    for marker in ("R5.1 2026 Annual Ledger", "2026 전체 Ledger", "loadUsPrimaryChart"):
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
        "r5_null_numeric_preserved": True,
        "canonical_ledger_source": "strategy_ledger",
        "trade_gate_unchanged": True,
        "web_read_only": True,
        "base_version": "vNext.7.4.27",
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
    with tempfile.TemporaryDirectory(prefix="kalman-v7428-") as td:
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
