#!/usr/bin/env bash
set -euo pipefail

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
GOOD_DEPLOYMENT="${KALMAN_HUB_GOOD_DEPLOYMENT:-dpl_5UY79dRUtszZNnUc3onHxd2Cj9EY}"
BASE_ALIAS="${KALMAN_HUB_BASE_ALIAS:-kalman-investment-hub-v2-base749.vercel.app}"
BASE_URL="https://${BASE_ALIAS}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/kalman-hub-shadow-proxy-${STAMP}"
SRC="${WORK}/source"
mkdir -p "${SRC}/api"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

for cmd in vercel python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"
done

echo "=================================================="
echo "Kalman Investment Hub vNext.7.4.11"
echo "Static clone + immutable backend proxy + SHADOW read-only"
echo "=================================================="
echo "Production : ${PROD_URL}"
echo "Base alias : ${BASE_URL}"
echo "Work       : ${WORK}"
echo

echo "[0/7] Vercel authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo
echo "[1/7] Pin immutable known-good backend to a stable public alias"
python3 - "${GOOD_DEPLOYMENT}" "${TEAM_ID}" "${BASE_ALIAS}" <<'PY'
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

deployment, team_id, alias = sys.argv[1:]

def find_token() -> str:
    env = os.environ.get("VERCEL_TOKEN", "").strip()
    if env:
        return env
    home = Path.home()
    candidates = [
        home / ".local/share/com.vercel.cli/auth.json",
        home / ".config/vercel/auth.json",
        home / ".vercel/auth.json",
    ]
    for base in (home / ".local/share", home / ".config"):
        if base.exists():
            candidates.extend(base.glob("**/com.vercel.cli/auth.json"))
    seen = set()
    for p in candidates:
        p = Path(p)
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        token = str(obj.get("token") or "").strip() if isinstance(obj, dict) else ""
        if token:
            return token
    raise SystemExit("[FAIL] Vercel auth token not found")

token = find_token()
query = urllib.parse.urlencode({"teamId": team_id})
url = f"https://api.vercel.com/v2/deployments/{deployment}/aliases?{query}"
body = json.dumps({"alias": alias, "redirect": None}).encode("utf-8")
req = urllib.request.Request(
    url,
    data=body,
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "kalman-base-alias/1.0",
    },
)
with urllib.request.urlopen(req, timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))
if payload.get("alias") != alias:
    raise SystemExit(f"[FAIL] alias assignment mismatch: {payload}")
print("[PASS] base alias assigned:", alias)
PY

curl -fsS --max-time 20 "${BASE_URL}/api/health" -o "${WORK}/base-health.json" || fail "base alias is not publicly reachable"
python3 - "${WORK}/base-health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("investment_hub_version")=="vNext.7.4.9", x
assert x.get("trade_enabled") is False, x
print("[PASS] immutable backend alias is public and healthy")
PY

echo
echo "[2/7] Fetch current production static bundle"
for file in index.html app.js style.css; do
  curl -fsS --max-time 30 "${PROD_URL}/${file}" -o "${SRC}/${file}" || fail "failed to fetch ${file}"
  [ -s "${SRC}/${file}" ] || fail "empty static file: ${file}"
done
echo "[PASS] index.html/app.js/style.css fetched"

echo
echo "[3/7] Patch SHADOW read-only UI"
python3 - "${SRC}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
index_path = root / "index.html"
app_path = root / "app.js"

index = index_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")

kr_tab = '<button class="tab" data-m="KR">한국장</button>'
if index.count(kr_tab) != 1:
    raise SystemExit("[FAIL] KR tab anchor missing")
index = index.replace(
    kr_tab,
    kr_tab + '\n      <button class="tab" data-m="SHADOW">Shadow</button>',
    1,
)

if "vNext.7.4.9 · MA20/60 + Actual Model Performance Tabs" in index:
    index = index.replace(
        "vNext.7.4.9 · MA20/60 + Actual Model Performance Tabs",
        "vNext.7.4.11 · Forward SHADOW Read Only",
        1,
    )
else:
    index = index.replace("vNext.7.4.9", "vNext.7.4.11")

anchor = """function renderMarket(m,j){
  if(m==='GLOBAL')return renderGlobal(j);if(m==='CRYPTO')return renderCrypto(j);if(m==='US')return renderUS(j);return renderKR(j)
}
"""
replacement = r"""function renderShadow(j){
  const signals=j.signals||{}, ranking=j.forward_ranking||[];
  const cards=['US','KR','BTC'].map(m=>{
    const s=signals[m]||{}, sig=String(s.signal||'—'), kind=sig==='BUY'?'warn':'';
    const score=s.probability!=null?`확률 ${pct(s.probability,100)}`:s.predicted_return!=null?`예상수익 ${pct(s.predicted_return,100)}`:'모델 점수 —';
    return `<div class="card"><div class="section-title"><h3>${m}</h3>${badge(sig,kind)}</div><div class="kpi">${esc(s.symbol||'—')}</div><div class="metric-line"><span class="muted">모델</span><b>${esc(s.model_family||'—')}</b></div><div class="metric-line"><span class="muted">Score</span><b>${score}</b></div><div class="metric-line"><span class="muted">결측률</span><b>${s.missing_feature_ratio==null?'—':pct(s.missing_feature_ratio,100)}</b></div><div class="small" style="margin-top:9px">${time(s.as_of)}</div></div>`;
  }).join('');
  const ranks=ranking.map((r,i)=>`<div class="top"><div class="rank">${r.forward_rank==null?i+1:r.forward_rank+1}</div><div><div class="asset">${esc(r.strategy||'—')}</div><div class="small">${esc(r.status||'—')}</div></div><div class="right"><b>${r.sharpe==null?'—':`Sharpe ${fmt(r.sharpe,2)}`}</b><div class="small">수익 ${r.total_return==null?'—':pct(r.total_return,100)} · MDD ${r.max_drawdown==null?'—':pct(r.max_drawdown,100)}</div></div></div>`).join('');
  return `<div class="summary">${badge('READ ONLY','ok')} ${badge(j.tracking_status||'SHADOW')} <span class="muted">갱신 ${time(j.updated_at)}</span></div><div class="notice">Forward SHADOW는 표시 전용입니다. 이 화면의 신호는 주문으로 전달되지 않습니다.</div><div class="grid section">${cards}</div><div class="card section"><div class="section-title"><h3>A/B/C Forward Ranking</h3><span class="muted">post-seed ${fmt(j.post_seed_return_rows,0)} rows</span></div>${ranks||'<div class="notice">아직 forward ranking 데이터가 부족합니다.</div>'}</div>`;
}
function renderMarket(m,j){
  if(m==='SHADOW')return renderShadow(j);if(m==='GLOBAL')return renderGlobal(j);if(m==='CRYPTO')return renderCrypto(j);if(m==='US')return renderUS(j);return renderKR(j)
}
"""
if anchor not in app:
    raise SystemExit("[FAIL] renderMarket anchor missing")
app = app.replace(anchor, replacement, 1)

assert 'data-m="SHADOW"' in index
assert "function renderShadow(j)" in app

index_path.write_text(index, encoding="utf-8")
app_path.write_text(app, encoding="utf-8")
print("[PASS] SHADOW tab + renderer patched")
PY

echo
echo "[4/7] Build one-function API proxy"
cat > "${SRC}/api/[...path].js" <<'JS'
const GOOD_URL = '__KALMAN_BASE_URL__';

function copyResponseHeaders(upstream, res) {
  for (const name of ['content-type', 'cache-control', 'etag', 'last-modified']) {
    const value = upstream.headers.get(name);
    if (value) res.setHeader(name, value);
  }
}

async function readBody(req) {
  if (req.method === 'GET' || req.method === 'HEAD') return undefined;
  if (req.body !== undefined && req.body !== null) {
    if (Buffer.isBuffer(req.body) || typeof req.body === 'string') return req.body;
    return JSON.stringify(req.body);
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return chunks.length ? Buffer.concat(chunks) : undefined;
}

module.exports = async function handler(req, res) {
  const here = new URL(req.url || '/api/health', 'https://kalman.local');
  const market = String(here.searchParams.get('market') || '').toUpperCase();

  if (here.pathname === '/api/dashboard' && market === 'SHADOW') {
    const base = String(process.env.TOSS_GATEWAY_URL || '').replace(/\/+$/, '');
    const secret = String(process.env.HUB_GATEWAY_SECRET || '');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');

    if (!base || !secret) {
      res.statusCode = 503;
      res.end(JSON.stringify({error:'SHADOW_GATEWAY_NOT_CONFIGURED'}));
      return;
    }

    try {
      const upstream = await fetch(base + '/api/shadow-bakeoff', {
        method: 'GET',
        headers: {
          'X-Gateway-Secret': secret,
          'Accept': 'application/json'
        },
        cache: 'no-store'
      });
      const text = await upstream.text();
      res.statusCode = upstream.status;
      res.end(text);
      return;
    } catch (err) {
      res.statusCode = 502;
      res.end(JSON.stringify({error:'SHADOW_GATEWAY_FETCH_FAILED'}));
      return;
    }
  }

  const target = new URL(req.url || '/api/health', GOOD_URL);

  const headers = {};
  for (const [key, value] of Object.entries(req.headers || {})) {
    const lower = key.toLowerCase();
    if (['host','connection','content-length','transfer-encoding'].includes(lower)) continue;
    if (value !== undefined) headers[key] = value;
  }

  const body = await readBody(req);

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body,
      redirect: 'manual',
      cache: 'no-store'
    });

    let text = await upstream.text();

    if (here.pathname === '/api/health' && upstream.ok) {
      try {
        const payload = JSON.parse(text);
        payload.investment_hub_version = 'vNext.7.4.11';
        payload.root_ui_version = 'vNext.7.4.11';
        payload.shadow_readonly_route = '/api/dashboard?market=SHADOW';
        payload.shadow_readonly = true;
        payload.trade_enabled = false;
        text = JSON.stringify(payload);
      } catch (_) {}
    }

    copyResponseHeaders(upstream, res);
    res.setHeader('Cache-Control', 'no-store');
    res.statusCode = upstream.status;
    res.end(text);
  } catch (err) {
    res.statusCode = 502;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({error:'KNOWN_GOOD_PROXY_FAILED'}));
  }
};
JS

python3 - "${SRC}/api/[...path].js" "${BASE_URL}" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
base=sys.argv[2].rstrip("/")
text=p.read_text(encoding="utf-8")
if text.count("__KALMAN_BASE_URL__") != 1:
    raise SystemExit("[FAIL] backend proxy placeholder mismatch")
p.write_text(text.replace("__KALMAN_BASE_URL__", base), encoding="utf-8")
print("[PASS] backend proxy target pinned:", base)
PY

cat > "${SRC}/vercel.json" <<'JSON'
{
  "version": 2
}
JSON

mkdir -p "${SRC}/.vercel"
cat > "${SRC}/.vercel/project.json" <<EOF
{"projectId":"${PROJECT_ID}","orgId":"${TEAM_ID}"}
EOF

echo "[PASS] immutable backend proxy prepared"

echo
echo "[5/7] Candidate deploy without production alias"
cd "${SRC}"
set +e
vercel deploy --prod --skip-domain --yes --scope "${TEAM_SLUG}" 2>&1 | tee "${WORK}/candidate.log"
DEPLOY_RC=${PIPESTATUS[0]}
set -e
[ "${DEPLOY_RC}" -eq 0 ] || fail "candidate deploy failed"

CANDIDATE="$(
  python3 - "${WORK}/candidate.log" <<'PY'
import re,sys
s=open(sys.argv[1], encoding="utf-8", errors="replace").read()
urls=re.findall(r'https://[A-Za-z0-9.-]+\.vercel\.app', s)
print(urls[-1] if urls else "")
PY
)"
[ -n "${CANDIDATE}" ] || fail "candidate URL not found"
echo "Candidate: ${CANDIDATE}"

vcurl() {
  local path="$1"
  local out="$2"
  vercel curl "${CANDIDATE}${path}" -sS >"$out"
}

echo
echo "[6/7] Candidate smoke tests"
vcurl "/api/health" "${WORK}/health.json"
vcurl "/api/account" "${WORK}/account.json"
vcurl "/api/dashboard?market=GLOBAL" "${WORK}/global.json"
vcurl "/api/dashboard?market=SHADOW" "${WORK}/shadow.json"
vercel curl "${CANDIDATE}/app.js" -sS > "${WORK}/app.js"

python3 - "${WORK}/health.json" "${WORK}/account.json" "${WORK}/global.json" "${WORK}/shadow.json" <<'PY'
import json,sys
h,a,g,s=(json.load(open(p,encoding="utf-8")) for p in sys.argv[1:])
assert h.get("investment_hub_version")=="vNext.7.4.11", h
assert h.get("trade_enabled") is False, h
assert a.get("status")=="READY", a
assert a.get("trade_execution") is False, a
assert g.get("payload") is not None and not g.get("error"), g
assert s.get("status")=="READY", s
assert s.get("schema_version")=="kalman-shadow-readonly-v1", s
inv=s.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
assert all(k in (s.get("signals") or {}) for k in ("US","KR","BTC"))
print("[PASS] candidate health/account/global/SHADOW")
PY

grep -q "renderShadow" "${WORK}/app.js" || fail "candidate UI missing SHADOW renderer"
echo "[PASS] candidate UI"

echo
echo "[7/7] Promote candidate"
vercel promote "${CANDIDATE}" --yes --scope "${TEAM_SLUG}" >/dev/null

READY=false
for _ in $(seq 1 45); do
  if curl -fsS --max-time 15 "${PROD_URL}/api/health" > "${WORK}/prod-health.json" 2>/dev/null; then
    if python3 - "${WORK}/prod-health.json" <<'PY' >/dev/null 2>&1
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
raise SystemExit(0 if x.get("investment_hub_version")=="vNext.7.4.11" else 1)
PY
    then
      READY=true
      break
    fi
  fi
  sleep 2
done

[ "${READY}" = true ] || {
  vercel promote "${GOOD_DEPLOYMENT}" --yes --scope "${TEAM_SLUG}" >/dev/null || true
  fail "production vNext.7.4.11 did not become healthy; restored known-good"
}

curl -fsS --max-time 20 "${PROD_URL}/api/dashboard?market=SHADOW" > "${WORK}/prod-shadow.json"
python3 - "${WORK}/prod-shadow.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="READY", x
assert x.get("schema_version")=="kalman-shadow-readonly-v1", x
inv=x.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
print("[PASS] production SHADOW read-only")
PY

echo
echo "[8/8] Complete"
echo "PRODUCTION_SHADOW_PROXY_GATE=PASS"
echo "WEB_DASHBOARD=${PROD_URL}"
