#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
VERSION_TAG="vNext.7.4.23"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$ROOT/kalman-hub-recovery/v7.4.23/source_manifest.ndjson"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-hub-v7423-${STAMP}"
SRC="$WORK/source"
mkdir -p "$SRC"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

need vercel
need python3
[ -f "$MANIFEST" ] || fail "missing source manifest: $MANIFEST"

echo "[0/6] Authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel authenticated"

echo "[1/6] Decode audited v7.4.23 source"
python3 - "$MANIFEST" "$SRC" <<'PY'
from pathlib import Path
import base64, json, sys

manifest, out = Path(sys.argv[1]), Path(sys.argv[2])
count = 0
for raw in manifest.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    row = json.loads(raw)
    rel = Path(row["file"])
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"unsafe manifest path: {rel}")
    dst = out / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(base64.b64decode(row["data_b64"]))
    count += 1
if count != 30:
    raise SystemExit(f"expected 30 files, got {count}")
print("decoded", count)
PY

grep -F "$VERSION_TAG" "$SRC/index.html" >/dev/null
grep -F "자동매매 · 실행 조건" "$SRC/index.html" >/dev/null
grep -F "LIVE_CANARY_TARGET_KRW=5000" "$SRC/app.js" >/dev/null
grep -F "/api/trading-status" "$SRC/api/assets.js" >/dev/null
node --check "$SRC/app.js" >/dev/null
node --check "$SRC/api/assets.js" >/dev/null
echo "[PASS] source validation"

echo "[2/6] Link Vercel project"
mkdir -p "$SRC/.vercel"
printf '{"projectId":"%s","orgId":"%s"}\n' "$PROJECT_ID" "$TEAM_ID" >"$SRC/.vercel/project.json"

echo "[3/6] Deploy candidate"
set +e
(
  cd "$SRC"
  vercel deploy --prod --skip-domain --yes --scope "$TEAM_SLUG"
) 2>&1 | tee "$WORK/deploy.log"
rc=${PIPESTATUS[0]}
set -e
[ "$rc" -eq 0 ] || fail "candidate deployment failed"

CANDIDATE="$(
python3 - "$WORK/deploy.log" <<'PY'
import re, sys
text=open(sys.argv[1],encoding="utf-8",errors="replace").read()
urls=re.findall(r"https://[A-Za-z0-9.-]+\.vercel\.app", text)
print(urls[-1] if urls else "")
PY
)"
[ -n "$CANDIDATE" ] || fail "candidate URL missing"
echo "[PASS] candidate=$CANDIDATE"

echo "[4/6] Candidate smoke tests"
vcurl(){
  local path="$1" out="$2"
  vercel curl "$CANDIDATE$path" -sS >"$out"
  [ -s "$out" ] || fail "empty response: $path"
}
vcurl "/" "$WORK/index.html"
vcurl "/app.js" "$WORK/app.js"
vcurl "/api/health" "$WORK/health.json"
vcurl "/api/assets?view=control" "$WORK/control.json"
vcurl "/api/dashboard?market=US" "$WORK/us.json"
set +e
vercel curl "$CANDIDATE/api/account" -sS >"$WORK/account.json"
set -e

python3 - "$WORK" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json, sys
root, version = Path(sys.argv[1]), sys.argv[2]
index=(root/"index.html").read_text(encoding="utf-8",errors="replace")
app=(root/"app.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"health.json").read_text())
control=json.loads((root/"control.json").read_text())
account=json.loads((root/"account.json").read_text())
us=json.loads((root/"us.json").read_text())

assert version in index
assert "자동매매 · 실행 조건" in index
assert 'id="operationsTab"' in index
assert "function readinessReasonLabel" in app
assert "account.trading_readiness" in app
assert health.get("investment_hub_version") == version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert control.get("schema_version") == "kalman-web-control-v2"
assert "signal_diagnostics" in control
assert account.get("trade_execution") is False
assert account.get("status") in {"READY","PARTIAL","OFFLINE"} or account.get("error")=="ACCOUNT_GATEWAY_NOT_CONFIGURED"
assert not us.get("error")
print("[PASS] candidate APIs/UI")
PY

echo "[5/6] Promote candidate"
vercel promote "$CANDIDATE" --yes --scope "$TEAM_SLUG" >/dev/null
echo "[PASS] promoted"

echo "[6/6] Production verification"
vercel curl "$PROD_URL/" -sS >"$WORK/prod-index.html"
vercel curl "$PROD_URL/app.js" -sS >"$WORK/prod-app.js"
vercel curl "$PROD_URL/api/health" -sS >"$WORK/prod-health.json"
set +e
vercel curl "$PROD_URL/api/account" -sS >"$WORK/prod-account.json"
set -e
vercel curl "$PROD_URL/api/assets?view=control" -sS >"$WORK/prod-control.json"

python3 - "$WORK" "$VERSION_TAG" <<'PY'
from pathlib import Path
import json, sys
root, version=Path(sys.argv[1]),sys.argv[2]
index=(root/"prod-index.html").read_text(encoding="utf-8",errors="replace")
app=(root/"prod-app.js").read_text(encoding="utf-8",errors="replace")
health=json.loads((root/"prod-health.json").read_text())
account=json.loads((root/"prod-account.json").read_text())
control=json.loads((root/"prod-control.json").read_text())
assert version in index
assert "자동매매 · 실행 조건" in index
assert 'id="operationsTab"' in index
assert "function readinessReasonLabel" in app
assert health.get("investment_hub_version") == version
assert health.get("trade_enabled") is False
assert health.get("account_trade_execution") is False
assert control.get("schema_version") == "kalman-web-control-v2"
assert account.get("trade_execution") is False
print("[PASS] production v7.4.23 visible and web remains read-only")
PY

echo "DONE: $PROD_URL"
