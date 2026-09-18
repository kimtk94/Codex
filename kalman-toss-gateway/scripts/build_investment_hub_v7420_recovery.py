from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "kalman-hub-recovery/v7.4.19/source_manifest.ndjson"
OUT_DIR = ROOT / "kalman-hub-recovery/v7.4.20"
BRANCH = "origin/feature/shadow-bakeoff-v1-20260913"
GATEWAY = "kalman-toss-gateway"
DEPLOY_SCRIPT = f"{GATEWAY}/scripts/deploy_investment_hub_account_krw.sh"
PATCH_FILES = [
    "patch_investment_hub_v7414.py",
    "patch_investment_hub_v7415.py",
    "patch_investment_hub_v7416.py",
    "patch_investment_hub_v7417.py",
    "patch_investment_hub_v7418.py",
]
TARGET = "vNext.7.4.20"


def git_show(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{BRANCH}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )


def decode_manifest(manifest: Path, out: Path) -> None:
    count = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        rel = Path(row["file"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"unsafe manifest path: {rel}")
        data = base64.b64decode(row["data_b64"])
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        count += 1
    if count != 30:
        raise SystemExit(f"expected 30 source files, decoded {count}")


def version(index_text: str) -> str:
    m = re.search(r"vNext\.7\.4\.(?:\d+|\d+-recovery)", index_text)
    return m.group(0) if m else ""


def normalize_recovery_to_v749(src: Path) -> None:
    idxp = src / "index.html"
    hp = src / "api/health.js"
    idx = idxp.read_text(encoding="utf-8")
    health = hp.read_text(encoding="utf-8")

    for old in ("vNext.7.4.19-recovery", "vNext.7.4.19"):
        idx = idx.replace(old, "vNext.7.4.9")
        health = health.replace(old, "vNext.7.4.9")

    if "WEB READ ONLY" in idx:
        idx = idx.replace("WEB READ ONLY", "TRADE OFF")
    if "vNext.7.4.9" not in idx or "TRADE OFF" not in idx:
        raise SystemExit("failed to normalize recovery source to v7.4.9")

    idxp.write_text(idx, encoding="utf-8")
    hp.write_text(health, encoding="utf-8")


def extract_upgrade_step(deploy_text: str, out: Path) -> None:
    anchor = deploy_text.find("[3/8] Patch account mapping + KRW reference values")
    if anchor < 0:
        raise SystemExit("upgrade anchor missing")
    start_marker = 'python3 - "${SRC}" <<\'PY\''
    start = deploy_text.find(start_marker, anchor)
    if start < 0:
        raise SystemExit("upgrade python heredoc start missing")
    start = deploy_text.find("\n", start) + 1
    end = deploy_text.find("\nPY\n", start)
    if end < 0:
        raise SystemExit("upgrade python heredoc end missing")
    out.write_text(deploy_text[start:end] + "\n", encoding="utf-8")


def run_patch_chain(src: Path, patch_root: Path) -> list[dict]:
    deploy_text = git_show(DEPLOY_SCRIPT)
    step = patch_root / "upgrade_step.py"
    extract_upgrade_step(deploy_text, step)

    scripts = patch_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in PATCH_FILES:
        (scripts / name).write_text(
            git_show(f"{GATEWAY}/scripts/{name}"),
            encoding="utf-8",
        )

    env = os.environ.copy()
    env["KALMAN_APP_ROOT"] = str(patch_root)
    history = []
    for _ in range(20):
        before = version((src / "index.html").read_text(encoding="utf-8"))
        if before == "vNext.7.4.18":
            break
        p = subprocess.run(
            [sys.executable, str(step), str(src)],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        after = version((src / "index.html").read_text(encoding="utf-8"))
        history.append({"before": before, "after": after, "rc": p.returncode, "log": p.stdout[-4000:]})
        if p.returncode != 0:
            raise SystemExit(f"patch chain failed {before}->{after}\n{p.stdout}")
        if after == before:
            raise SystemExit(f"patch chain made no progress at {before}\n{p.stdout}")
    else:
        raise SystemExit("patch chain exceeded iteration limit")

    if version((src / "index.html").read_text(encoding="utf-8")) != "vNext.7.4.18":
        raise SystemExit("patch chain did not reach v7.4.18")
    return history


def apply_v7420_delta(src: Path) -> None:
    appp = src / "app.js"
    idxp = src / "index.html"
    hp = src / "api/health.js"

    app = appp.read_text(encoding="utf-8")
    idx = idxp.read_text(encoding="utf-8")
    health = hp.read_text(encoding="utf-8")

    ledger_patch = (ROOT / f"{GATEWAY}/scripts/ledger_semantics_patch.js").read_text(encoding="utf-8").strip()
    if "KALMAN_LEDGER_SEMANTICS_V1" not in app:
        app = app.rstrip() + "\n\n" + ledger_patch + "\n"

    if idx.count("TRADE OFF") != 1:
        raise SystemExit(f"expected one TRADE OFF badge, got {idx.count('TRADE OFF')}")
    idx = idx.replace("TRADE OFF", "WEB READ ONLY", 1)

    for old in ("vNext.7.4.18",):
        idx = idx.replace(old, TARGET)
        app = app.replace(old, TARGET)
        health = health.replace(old, TARGET)

    if TARGET not in idx or TARGET not in health:
        raise SystemExit("v7.4.20 version markers missing")
    if "WEB READ ONLY" not in idx or "TRADE OFF" in idx:
        raise SystemExit("read-only badge patch failed")

    appp.write_text(app, encoding="utf-8")
    idxp.write_text(idx, encoding="utf-8")
    hp.write_text(health, encoding="utf-8")


def validate(src: Path) -> dict:
    api = sorted((src / "api").rglob("*.js"))
    if len(api) != 12:
        raise SystemExit(f"API function count changed: {len(api)}")

    idx = (src / "index.html").read_text(encoding="utf-8")
    app = (src / "app.js").read_text(encoding="utf-8")
    health = (src / "api/health.js").read_text(encoding="utf-8")

    markers = {
        "index": [
            TARGET,
            "WEB READ ONLY",
            "Investment Intelligence",
            "commandHealth",
            "universeTab",
            "Command Center + Universe View",
        ],
        "app": [
            "UNIVERSE_BASELINE_TOTAL=102",
            "function loadUniverse()",
            "US R5.1 UNIVERSE",
            "renderNextActions",
            "R5.1 2026 Annual Ledger",
            "STRICT_TOP3_ACTUAL_LEDGER",
            "KALMAN_LEDGER_SEMANTICS_V1",
        ],
        "health": [TARGET, "trade_enabled", "account_trade_execution"],
    }
    for name, wanted in markers.items():
        text = {"index": idx, "app": app, "health": health}[name]
        missing = [x for x in wanted if x not in text]
        if missing:
            raise SystemExit(f"{name} missing markers: {missing}")

    if "TRADE OFF" in idx:
        raise SystemExit("stale TRADE OFF remains")

    regression = []
    for p in list((src / "api").rglob("*.js")) + list((src / "lib").rglob("*.js")):
        t = p.read_text(encoding="utf-8")
        if "req.query" in t or "url.parse(" in t:
            regression.append(p.relative_to(src).as_posix())
    if regression:
        raise SystemExit(f"query parser regression: {regression}")

    # Syntax-check all JS when Node is present on the runner.
    if shutil.which("node"):
        for p in sorted(src.rglob("*.js")):
            subprocess.run(["node", "--check", str(p)], check=True, stdout=subprocess.DEVNULL)

    return {
        "source_files": len([p for p in src.rglob("*") if p.is_file()]),
        "api_functions": len(api),
        "version": TARGET,
        "universe": True,
        "command_center": True,
        "ledger_semantics": True,
        "web_read_only": True,
    }


def emit_source_manifest(src: Path, out: Path) -> None:
    rows = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rel = p.relative_to(src).as_posix()
        rows.append(json.dumps(
            {"file": rel, "data_b64": base64.b64encode(p.read_bytes()).decode("ascii")},
            separators=(",", ":"),
            ensure_ascii=False,
        ))
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def node_wrapper(source: bytes) -> str:
    payload = base64.b64encode(gzip.compress(source, compresslevel=9, mtime=0)).decode("ascii")
    return (
        "const z=require('zlib');"
        f"const s=z.gunzipSync(Buffer.from('{payload}','base64')).toString('utf8');"
        "module._compile(s,__filename);"
    )


def browser_loader() -> str:
    url = "https://raw.githubusercontent.com/kimtk94/Codex/main/kalman-hub-recovery/v7.4.20/source_manifest.ndjson"
    return (
        "(()=>{const U=" + json.dumps(url) + ";"
        "fetch(U,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('manifest '+r.status);return r.text()})"
        ".then(t=>{for(const l of t.split(/\\r?\\n/)){if(!l.trim())continue;const x=JSON.parse(l);"
        "if(x.file==='app.js'){const b=Uint8Array.from(atob(x.data_b64),c=>c.charCodeAt(0));"
        "(0,Function)(new TextDecoder().decode(b))();return}}throw Error('app.js missing')})"
        ".catch(e=>{console.error(e);const c=document.querySelector('#content');"
        "if(c)c.innerHTML='<div class=\"card bad\">Kalman app recovery failed</div>'})})();"
    )


def emit_vercel_manifest(src: Path, out: Path) -> int:
    files = []
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        rel = p.relative_to(src).as_posix()
        if rel == "app.js":
            data = browser_loader()
        elif p.suffix == ".js" and (rel.startswith("api/") or rel.startswith("lib/")):
            data = node_wrapper(p.read_bytes())
        else:
            data = p.read_text(encoding="utf-8")
        files.append({"file": rel, "data": data})
    out.write_text(json.dumps(files, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out.stat().st_size


def main() -> int:
    if not BASE_MANIFEST.exists():
        raise SystemExit(f"missing {BASE_MANIFEST}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kalman-v7420-") as td:
        td = Path(td)
        src = td / "source"
        src.mkdir()
        decode_manifest(BASE_MANIFEST, src)
        normalize_recovery_to_v749(src)
        history = run_patch_chain(src, td / "branch-patches")
        apply_v7420_delta(src)
        report = validate(src)

        source_manifest = OUT_DIR / "source_manifest.ndjson"
        vercel_manifest = OUT_DIR / "vercel_manifest.json"
        emit_source_manifest(src, source_manifest)
        compact_bytes = emit_vercel_manifest(src, vercel_manifest)

        report["compact_manifest_bytes"] = compact_bytes
        report["patch_history"] = history
        report["source_manifest_sha256"] = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
        report["vercel_manifest_sha256"] = hashlib.sha256(vercel_manifest.read_bytes()).hexdigest()
        (OUT_DIR / "build_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
