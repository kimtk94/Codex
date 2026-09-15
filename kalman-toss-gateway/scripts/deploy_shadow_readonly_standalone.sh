#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="${KALMAN_SOURCE_ROOT:-/opt/kalman/src/Codex/kalman-toss-gateway}"
TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
SOURCE_PROJECT_ID="${VERCEL_SOURCE_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
SHADOW_PROJECT_NAME="${KALMAN_SHADOW_WEB_PROJECT:-kalman-shadow-readonly}"
STABLE_URL="https://${SHADOW_PROJECT_NAME}.vercel.app"
WORK="/tmp/kalman-shadow-readonly-$(date -u +%Y%m%dT%H%M%SZ)"
APP_DIR="${WORK}/app"
ENV_PULL="${WORK}/source-production.env"

fail(){ echo "[FAIL] $*" >&2; exit 1; }

for cmd in vercel python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"
done

[ -d "$SRC_ROOT/shadow-web" ] || fail "shadow-web source missing: $SRC_ROOT/shadow-web"

mkdir -p "$APP_DIR"
cp -a "$SRC_ROOT/shadow-web/." "$APP_DIR/"

echo "============================================================"
echo "KALMAN — STANDALONE SHADOW READ-ONLY WEB"
echo "============================================================"

echo
echo "[1/6] Vercel authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo
echo "[2/6] Pull existing production gateway configuration without printing secrets"
mkdir -p "$WORK/source-link/.vercel"
cat > "$WORK/source-link/.vercel/project.json" <<EOF
{"projectId":"$SOURCE_PROJECT_ID","orgId":"$TEAM_ID"}
EOF

(
  cd "$WORK/source-link"
  vercel env pull "$ENV_PULL" --environment=production --yes >/dev/null
)

python3 - "$ENV_PULL" <<'PY'
from pathlib import Path
import sys

def parse_env(path):
    out={}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key,value=line.split("=",1)
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in {'"', "'"}:
            value=value[1:-1]
        out[key.strip()]=value
    return out

x=parse_env(sys.argv[1])
for k in ("TOSS_GATEWAY_URL","HUB_GATEWAY_SECRET"):
    if not str(x.get(k) or "").strip():
        raise SystemExit(f"[FAIL] missing production env: {k}")
print("[PASS] source gateway configuration available")
PY

echo
echo "[3/6] Create/reuse isolated Vercel project and upsert encrypted env"
python3 - "$ENV_PULL" "$TEAM_ID" "$SHADOW_PROJECT_NAME" "$APP_DIR" <<'PY'
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
env_file, team_id, project_name, app_dir = sys.argv[1:]

def parse_env(path):
    out={}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key,value=line.split("=",1)
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in {'"', "'"}:
            value=value[1:-1]
        out[key.strip()]=value
    return out

env=parse_env(env_file)
gateway=str(env.get("TOSS_GATEWAY_URL") or "").strip()
secret=str(env.get("HUB_GATEWAY_SECRET") or "").strip()
if not gateway or not secret:
    raise SystemExit("[FAIL] required source env missing")

def find_token():
    v=os.environ.get("VERCEL_TOKEN","").strip()
    if v:
        return v
    home=Path.home()
    candidates=[
        home/".local/share/com.vercel.cli/auth.json",
        home/".config/vercel/auth.json",
        home/".vercel/auth.json",
    ]
    for base in (home/".local/share",home/".config"):
        if base.exists():
            candidates.extend(base.glob("**/com.vercel.cli/auth.json"))
    seen=set()
    for p in candidates:
        p=Path(p)
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        try:
            obj=json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        token=str(obj.get("token") or "").strip() if isinstance(obj,dict) else ""
        if token:
            return token
    raise SystemExit("[FAIL] Vercel token not found")

token=find_token()
headers={
    "Authorization":f"Bearer {token}",
    "Content-Type":"application/json",
    "Accept":"application/json",
    "User-Agent":"kalman-shadow-readonly/1.0",
}
q=urllib.parse.urlencode({"teamId":team_id})

def request(method,url,body=None,allow_404=False):
    data=None if body is None else json.dumps(body).encode("utf-8")
    req=urllib.request.Request(url,data=data,method=method,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            return r.status,json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw=e.read().decode("utf-8",errors="replace")
        if allow_404 and e.code==404:
            return 404,{}
        raise SystemExit(f"[FAIL] Vercel API {method} {url}: HTTP {e.code} {raw[:300]}")

status,project=request("GET",f"https://api.vercel.com/v9/projects/{urllib.parse.quote(project_name,safe='')}?{q}",allow_404=True)
if status==404:
    _,project=request("POST",f"https://api.vercel.com/v11/projects?{q}",{"name":project_name})
    print("[PASS] project created")
else:
    print("[PASS] project reused")

project_id=str(project.get("id") or "").strip()
if not project_id:
    raise SystemExit("[FAIL] project id missing")

env_body=[
    {"key":"TOSS_GATEWAY_URL","value":gateway,"type":"encrypted","target":["production"]},
    {"key":"HUB_GATEWAY_SECRET","value":secret,"type":"encrypted","target":["production"]},
]
request(
    "POST",
    f"https://api.vercel.com/v10/projects/{project_id}/env?upsert=true&{q}",
    env_body,
)
print("[PASS] encrypted production env upserted")

vercel_dir=Path(app_dir)/".vercel"
vercel_dir.mkdir(parents=True,exist_ok=True)
(vercel_dir/"project.json").write_text(
    json.dumps({"projectId":project_id,"orgId":team_id}),
    encoding="utf-8",
)
(Path(app_dir)/".kalman-project-id").write_text(project_id,encoding="utf-8")
PY

rm -f "$ENV_PULL"
echo "[PASS] temporary source env removed"

echo
echo "[4/6] Deploy standalone SHADOW web"
cd "$APP_DIR"
set +e
vercel deploy --prod --yes 2>&1 | tee "$WORK/deploy.log"
DEPLOY_RC=${PIPESTATUS[0]}
set -e
[ "$DEPLOY_RC" -eq 0 ] || fail "shadow web deployment failed"

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
vercel curl "$DEPLOY_URL/api/health" -sS > "$WORK/health.json"
vercel curl "$DEPLOY_URL/api/shadow" -sS > "$WORK/shadow.json"
vercel curl "$DEPLOY_URL/" -sS > "$WORK/index.html"

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
print("[PASS] standalone SHADOW read-only smoke")
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
)
raise SystemExit(0 if ok else 1)
PY
  then
    STABLE_READY=true
    break
  fi
  sleep 2
done

[ "$STABLE_READY" = true ] || fail "stable SHADOW production domain did not become READY"
echo "[PASS] stable SHADOW production domain"

echo
echo "[6/6] Complete"
echo "SHADOW_READONLY_WEB_GATE=PASS"
echo "SHADOW_WEB=$STABLE_URL"
echo "DEPLOYMENT_URL=$DEPLOY_URL"
echo "MAIN_WEB=https://kalman-investment-hub-v2.vercel.app"
echo "TRADE_EXECUTION=false"
