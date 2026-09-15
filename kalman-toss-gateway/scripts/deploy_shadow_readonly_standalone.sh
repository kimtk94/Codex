#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="${KALMAN_SOURCE_ROOT:-/opt/kalman/src/Codex/kalman-toss-gateway}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
SHADOW_PROJECT_NAME="${KALMAN_SHADOW_WEB_PROJECT:-kalman-shadow-readonly}"
SHADOW_PROJECT_ID="${KALMAN_SHADOW_PROJECT_ID:-prj_jOPKhEQPtwLd845CQUYGq8x2jLP0}"
STABLE_URL="https://${SHADOW_PROJECT_NAME}.vercel.app"
WORK="/tmp/kalman-shadow-readonly-$(date -u +%Y%m%dT%H%M%SZ)"
APP_DIR="${WORK}/app"

fail(){ echo "[FAIL] $*" >&2; exit 1; }

for cmd in vercel python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"
done

[ -d "$SRC_ROOT/shadow-web" ] || fail "shadow-web source missing: $SRC_ROOT/shadow-web"

STATUS_PATH="${KALMAN_SHADOW_BAKEOFF_STATUS:-}"
if [ -z "$STATUS_PATH" ]; then
  STATUS_PATH="$(python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

p=Path(sys.argv[1])
v={}
if p.is_file():
    for raw in p.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,val=line.split("=",1)
        val=val.strip()
        if len(val)>=2 and val[0]==val[-1] and val[0] in {'"', "'"}:
            val=val[1:-1]
        v[k.strip()]=val

data_root=v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
model_root=v.get("KALMAN_MODEL_V2_ROOT") or str(Path(data_root)/"Market_Model_V2")
print(v.get("KALMAN_SHADOW_BAKEOFF_STATUS") or str(Path(model_root)/"shadow_bakeoff/v1/latest/bakeoff_status.json"))
PY
)"
fi

[ -f "$STATUS_PATH" ] || fail "SHADOW bakeoff status missing: $STATUS_PATH"

mkdir -p "$APP_DIR"
cp -a "$SRC_ROOT/shadow-web/." "$APP_DIR/"

echo "============================================================"
echo "KALMAN — STANDALONE SHADOW SNAPSHOT WEB"
echo "============================================================"

echo
echo "[1/6] Vercel authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo
echo "[2/6] Validate fresh read-only SHADOW snapshot"
python3 - "$STATUS_PATH" "$APP_DIR/api/shadow.js" <<'PY'
from __future__ import annotations
import base64
import json
from pathlib import Path
import sys

src=Path(sys.argv[1])
dst=Path(sys.argv[2])
x=json.loads(src.read_text(encoding="utf-8"))

if x.get("status") != "READY":
    raise SystemExit(f"[FAIL] SHADOW status={x.get('status')!r}")

signals=x.get("signal_status") or x.get("signals") or {}
for market in ("US","KR","BTC"):
    s=signals.get(market)
    if not isinstance(s,dict):
        raise SystemExit(f"[FAIL] missing SHADOW signal: {market}")

inv=x.get("invariants") or {}
for key in (
    "production_write",
    "neon_write",
    "toss_execution",
    "live_execution",
    "auto_trade_visible",
    "dashboard_snapshot_created",
):
    if key in inv and inv.get(key) is not False:
        raise SystemExit(f"[FAIL] unsafe invariant {key}={inv.get(key)!r}")

# Gateway normalizes signal_status -> signals. Preserve the existing public API
# schema so the UI does not care whether the source is gateway or snapshot.
safe=dict(x)
safe["schema_version"]="kalman-shadow-readonly-v1"
safe["signals"]=signals
safe.pop("signal_status",None)
safe["invariants"]={
    **inv,
    "read_only":True,
    "trade_execution":False,
}
safe["snapshot_source"]="server-bakeoff-file"

raw=json.dumps(safe,ensure_ascii=False,separators=(",",":")).encode("utf-8")
b64=base64.b64encode(raw).decode("ascii")

js=f"""module.exports = async function handler(req,res){{
  const raw=Buffer.from('{b64}','base64').toString('utf8');
  res.setHeader('Cache-Control','no-store');
  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('X-Kalman-Shadow-Source','snapshot');
  res.statusCode=200;
  res.end(raw);
}};
"""
dst.write_text(js,encoding="utf-8")

print("[PASS] snapshot READY")
print("updated_at=",safe.get("updated_at"))
for market in ("US","KR","BTC"):
    s=signals.get(market) or {}
    print(market,"as_of=",s.get("as_of"),"signal=",s.get("signal"))
print("[PASS] trade_execution=false")
PY

echo
echo "[3/6] Link isolated Vercel project"
mkdir -p "$APP_DIR/.vercel"
cat > "$APP_DIR/.vercel/project.json" <<EOF
{"projectId":"$SHADOW_PROJECT_ID","orgId":"$TEAM_ID"}
EOF
echo "[PASS] project linked: $SHADOW_PROJECT_NAME"

echo
echo "[4/6] Deploy standalone SHADOW snapshot"
cd "$APP_DIR"
set +e
vercel deploy --prod --yes 2>&1 | tee "$WORK/deploy.log"
DEPLOY_RC=${PIPESTATUS[0]}
set -e
[ "$DEPLOY_RC" -eq 0 ] || fail "shadow snapshot deployment failed"

DEPLOY_URL="$(
  python3 - "$WORK/deploy.log" <<'PY'
import re,sys
s=open(sys.argv[1],encoding="utf-8",errors="replace").read()
urls=re.findall(r'https://[A-Za-z0-9.-]+\.vercel\.app',s)
print(urls[-1] if urls else "")
PY
)"
[ -n "$DEPLOY_URL" ] || fail "deployment URL not found"
echo "deployment=$DEPLOY_URL"

echo
echo "[5/6] Smoke deployment"
vercel curl "$DEPLOY_URL/api/health" -- --silent --show-error > "$WORK/health.json"
vercel curl "$DEPLOY_URL/api/shadow" -- --silent --show-error > "$WORK/shadow.json"
vercel curl "$DEPLOY_URL/" -- --silent --show-error > "$WORK/index.html"

python3 - "$WORK/health.json" "$WORK/shadow.json" <<'PY'
import json,sys
h=json.load(open(sys.argv[1],encoding="utf-8"))
s=json.load(open(sys.argv[2],encoding="utf-8"))
assert h.get("status")=="ok",h
assert h.get("read_only") is True,h
assert h.get("trade_execution") is False,h
assert s.get("status")=="READY",s
assert s.get("schema_version")=="kalman-shadow-readonly-v1",s
inv=s.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
assert all(m in (s.get("signals") or {}) for m in ("US","KR","BTC"))
assert s.get("snapshot_source")=="server-bakeoff-file"
print("[PASS] standalone SHADOW snapshot smoke")
PY

grep -q "Kalman Forward SHADOW" "$WORK/index.html" || fail "SHADOW UI marker missing"

echo
echo "[5b/6] Verify stable production domain"
STABLE_READY=false
for _ in $(seq 1 45); do
  : >"$WORK/stable-health.json"
  : >"$WORK/stable-shadow.json"
  curl -fsS --max-time 15 "$STABLE_URL/api/health" -o "$WORK/stable-health.json" 2>/dev/null || true
  curl -fsS --max-time 15 "$STABLE_URL/api/shadow" -o "$WORK/stable-shadow.json" 2>/dev/null || true

  if python3 - "$WORK/stable-health.json" "$WORK/stable-shadow.json" <<'PY' >/dev/null 2>&1
import json,sys
from pathlib import Path
try:
    h=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
    s=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8").strip())
except Exception:
    raise SystemExit(1)

ok=(
    h.get("status")=="ok"
    and h.get("read_only") is True
    and s.get("status")=="READY"
    and s.get("schema_version")=="kalman-shadow-readonly-v1"
    and s.get("snapshot_source")=="server-bakeoff-file"
)
raise SystemExit(0 if ok else 1)
PY
  then
    STABLE_READY=true
    break
  fi
  sleep 2
done

[ "$STABLE_READY" = true ] || fail "stable SHADOW snapshot domain did not become READY"
echo "[PASS] stable SHADOW production domain"

echo
echo "[6/6] Complete"
echo "SHADOW_READONLY_WEB_GATE=PASS"
echo "SHADOW_SOURCE=snapshot"
echo "SHADOW_WEB=$STABLE_URL"
echo "DEPLOYMENT_URL=$DEPLOY_URL"
echo "MAIN_WEB=https://kalman-investment-hub-v2.vercel.app"
echo "TRADE_EXECUTION=false"
