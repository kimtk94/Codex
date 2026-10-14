"""Build the complete Kalman Investment Hub v7.4.36 without Vercel access.

- No Vercel commands, API fetches, tokens, DB connections, or deploy.
- The historical builders generate 30 files from pinned GitHub manifest.
- Inspect the FINAL JS bundle, NOT merely the patched v7.4.24 generator.
- Save only filenames, hashes and gate decisions (not source/data payload).
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "kalman-toss-gateway/scripts/build_investment_hub_v7436_shadow_freshness.py"
MANIFEST = ROOT / "kalman-hub-recovery/v7.4.36/source_manifest.ndjson"
VERSION = "vNext.7.4.36"
EXPECTED_NAMES = {
    "api/analyze.js", "api/assets.js", "api/cache-status.js", "api/health.js",
    "api/history.js", "api/ingest/etf.js", "api/ingest/manual-snapshot.js",
    "api/market.js", "api/position-ledger-tick.js", "api/position-ledger.js",
    "api/position.js", "api/risk.js", "app.js", "data/etf-snapshot.json",
    "data/latest-7asset-snapshot.json", "data/qld-oos.json", "index.html",
    "lib/assets-payload.js", "lib/auth.js", "lib/champion-seed.js",
    "lib/core.js", "lib/durable-store.js", "lib/history.js",
    "lib/position-ledger-actions.js", "lib/position-ledger.js",
    "lib/position-management.js", "lib/runtime-cache.js", "package.json",
    "style.css", "vercel.json",
}


class ReleaseGateError(RuntimeError):
    pass


def decode_manifest(blob: str) -> dict[str, bytes]:
    items = {}
    lines = [x for x in blob.splitlines() if x.strip()]
    if len(lines) != 30:
        raise ReleaseGateError("MANIFEST_WRONG_LENGTH")
    for line in lines:
        row = json.loads(line)
        if set(row) != {"file", "data_b64"}:
            raise ReleaseGateError("UNEXPECTED_MANIFEST_KEYS")
        name = row["file"]
        if not isinstance(name, str) or not name:
            raise ReleaseGateError("BAD_FILE_NAME")
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or str(p) != name or name in items:
            raise ReleaseGateError("UNSAFE_OR_DUPLICATE_PATH")
        try:
            items[name] = base64.b64decode(row["data_b64"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ReleaseGateError("BAD_BASE64") from exc
    if set(items) != EXPECTED_NAMES:
        raise ReleaseGateError("UNEXPECTED_SOURCE_FILES")
    return items


def verify_source(files: dict[str, bytes]) -> dict:
    def fail(reason: str) -> None:
        raise ReleaseGateError(reason)
    index = files["index.html"].decode("utf-8")
    app = files["app.js"].decode("utf-8")
    api = files["api/assets.js"].decode("utf-8")
    health = files["api/health.js"].decode("utf-8")
    config = files["vercel.json"].decode("utf-8")
    if VERSION not in index or VERSION not in health:
        fail("VERSION_INCONSISTENCY")
    if "trade_enabled:false" not in health or "account_trade_execution:false" not in health:
        fail("WEB_READ_ONLY_CONTRACT_MISSING")
    if "v_live_trade_ledger" not in api or "net_return" not in api:
        fail("LIVE_LEDGER_API_CONTRACT_MISSING")
    # The existing production view contains five known P1 overstatements.
    # Until independently verified broker provenance exists, the generated API
    # MUST return typed NULL for monetary net return and cost, not stale values.
    if ("NULL::numeric AS net_return" not in api
            or "NULL::numeric AS round_trip_cost_bps" not in api):
        fail("UNGUARDED_NET_RETURN_API_CONTRACT")
    if "realized_return_pct,net_return,round_trip_cost_bps" in api:
        fail("RAW_NET_RETURN_LEAKAGE")
    if "function renderExecutionLedger(ctl)" not in app:
        fail("EXECUTION_LEDGER_UI_MISSING")
    # Require all evidence flags IN THE FINAL produced JS, not in a generator.
    for marker in (
        "function verifiedNet(x)",
        "net_return_evidence_status==='BROKER_RECONCILED'",
        "x.independent_order_manifest_verified===true",
        "x.fee_currency_verified===true",
        "x.position_fill_coverage_verified===true",
        "net=verifiedNet(x)",
        "검증 전",
    ):
        if marker not in app:
            fail("FINAL_UI_P1_GUARD_MISSING:" + marker)
    if "var gross=n(x.realized_return_pct),net=n(x.net_return)" in app:
        fail("UNGUARDED_NET_RENDER_PRESENT")
    if not isinstance(json.loads(config), dict):
        fail("INVALID_VERCEL_CONFIG")
    return {
        "decision": "OFFLINE_BUILD_PASS_RELEASE_HOLD",
        "version": VERSION,
        "manifest_files": len(files),
        "api_js_files": sum(x.startswith("api/") and x.endswith(".js") for x in files),
        "ui_net_evidence_guard": True,
        "api_net_return_masked": True,
        "web_read_only_contract": True,
        "release_authorized": False,
        "source_hashes": {
            name: hashlib.sha256(files[name]).hexdigest()
            for name in ("index.html", "app.js", "api/assets.js",
                         "api/health.js", "vercel.json")
        },
    }


def build_and_verify():
    if not BUILDER.is_file():
        raise ReleaseGateError("BUILDER_NOT_FOUND")
    # No Vercel CLI or production actions. Builders invoke only local scripts.
    subprocess.run([sys.executable, str(BUILDER)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=240)
    if not MANIFEST.is_file():
        raise ReleaseGateError("BUILT_MANIFEST_NOT_FOUND")
    files = decode_manifest(MANIFEST.read_text(encoding="utf-8"))
    result = verify_source(files)
    # JS syntax-check only, NEVER execute the API code.
    with tempfile.TemporaryDirectory(prefix="kalman-build-gate-") as temp:
        for name in ("app.js", "api/assets.js", "api/health.js"):
            outfile = Path(temp) / name.replace("/", "_")
            outfile.write_bytes(files[name])
            subprocess.run(["node", "--check", str(outfile)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=15)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="")
    args = p.parse_args()
    result = build_and_verify()
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "source_hashes"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
