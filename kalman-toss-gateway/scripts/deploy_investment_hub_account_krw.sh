#!/usr/bin/env bash
set -euo pipefail

# Recover the last known-good full Investment Hub deployment, recover its exact
# source through the authenticated Vercel API, patch only the account UI, build
# a production-environment candidate without assigning the production domain,
# smoke-test it, then promote it.
#
# This script never changes Toss live-trading gates.

TEAM_ID="${VERCEL_TEAM_ID:-team_eklxTMfdySLBHexmheTiWGCE}"
TEAM_SLUG="${VERCEL_TEAM_SLUG:-insk1285-9320s-projects}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1}"
PROJECT_NAME="${VERCEL_PROJECT_NAME:-kalman-investment-hub-v2}"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"

# Full 12-function redeploy created after TOSS_GATEWAY_URL was configured.
GOOD_DEPLOYMENT="${KALMAN_HUB_GOOD_DEPLOYMENT:-dpl_5UY79dRUtszZNnUc3onHxd2Cj9EY}"
GOOD_URL="${KALMAN_HUB_GOOD_URL:-https://kalman-investment-hub-v2-77jlvdtk8-insk1285-9320s-projects.vercel.app}"

STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-hub-v7411-${STAMP}"
SRC="${WORK}/source"
mkdir -p "${SRC}"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

need vercel
need python3
need curl
need tar

echo "=================================================="
echo "Kalman Investment Hub vNext.7.4.11"
echo "Account USD/KRW + SHADOW read-only"
echo "=================================================="
echo "Production : ${PROD_URL}"
echo "Base       : ${GOOD_DEPLOYMENT}"
echo "Work       : ${WORK}"
echo

echo "[0/8] Vercel authentication"
vercel whoami >/dev/null
echo "[PASS] Vercel CLI authenticated"

echo
echo "[1/8] Ensure known-good full production"

health_ok() {
  local file="$1"
  python3 - "$file" <<'PY' >/dev/null 2>&1
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
try:
    raw=p.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(1)
    x=json.loads(raw)
except Exception:
    raise SystemExit(1)

required = (
    x.get("investment_hub_version") == "vNext.7.4.9"
    and x.get("account_gateway_configured") is True
    and x.get("account_gateway_secret_configured") is True
    and x.get("account_trade_execution") is False
    and x.get("trade_enabled") is False
)
routes=x.get("required_routes") or []
required = required and "/api/dashboard" in routes and "/api/account" in routes
raise SystemExit(0 if required else 1)
PY
}

# Avoid unnecessary alias churn when Production is already the healthy
# 12-function vNext.7.4.9 base.
CURRENT_HEALTH="${WORK}/current-health.json"
if curl -fsS --max-time 10 "${PROD_URL}/api/health" >"${CURRENT_HEALTH}" 2>/dev/null \
   && health_ok "${CURRENT_HEALTH}"; then
  echo "[PASS] healthy vNext.7.4.9 full production already active; promotion skipped"
else
  echo "[INFO] restoring known-good 12-function production"
  vercel promote "${GOOD_URL}" --yes --scope "${TEAM_SLUG}" >/dev/null

  RESTORED=false
  for i in $(seq 1 45); do
    # During Vercel alias propagation the canonical host can briefly return
    # an empty/non-JSON body. Treat that as 'not ready yet', never as a fatal
    # JSON parsing error.
    : >"${WORK}/restored-health.json"
    curl -fsS --max-time 10 "${PROD_URL}/api/health" \
      >"${WORK}/restored-health.json" 2>/dev/null || true

    if health_ok "${WORK}/restored-health.json"; then
      RESTORED=true
      break
    fi

    sleep 2
  done

  [ "${RESTORED}" = true ] || fail "known-good production restore verification failed"
  echo "[PASS] known-good production restored"
fi

account_ok() {
  local file="$1"
  python3 - "$file" <<'PY' >/dev/null 2>&1
import json, sys
from pathlib import Path
try:
    raw=Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    x=json.loads(raw)
except Exception:
    raise SystemExit(1)
parts=x.get("parts") or {}
items=(((x.get("holdings") or {}).get("result") or {}).get("items") or [])
ok=(
    x.get("status") == "READY"
    and x.get("trade_execution") is False
    and bool(items)
    and all((parts.get(k) or {}).get("ok") is True for k in (
        "accounts","holdings","buying_power_usd","buying_power_krw"
    ))
)
raise SystemExit(0 if ok else 1)
PY
}

dashboard_ok() {
  local file="$1"
  python3 - "$file" <<'PY' >/dev/null 2>&1
import json, sys
from pathlib import Path
try:
    raw=Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    x=json.loads(raw)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if not x.get("error") and x.get("payload") is not None else 1)
PY
}

wait_json_route() {
  local url="$1"
  local file="$2"
  local checker="$3"
  local label="$4"
  local attempts="${5:-45}"

  for _ in $(seq 1 "$attempts"); do
    : >"$file"
    curl -fsS --max-time 20 "$url" >"$file" 2>/dev/null || true
    if "$checker" "$file"; then
      echo "[PASS] $label"
      return 0
    fi
    sleep 2
  done

  echo "[FAIL] $label did not become valid JSON/READY" >&2
  echo "[INFO] last response preview:" >&2
  head -c 500 "$file" >&2 || true
  echo >&2
  return 1
}

wait_json_route   "${PROD_URL}/api/account"   "${WORK}/restored-account.json"   account_ok   "account READY" || fail "account restore verification failed"

python3 - "${WORK}/restored-account.json" <<'PY'
import json, sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
items=(((x.get("holdings") or {}).get("result") or {}).get("items") or [])
print(f"[PASS] account holdings={len(items)}")
PY

wait_json_route   "${PROD_URL}/api/dashboard?market=GLOBAL"   "${WORK}/restored-dashboard.json"   dashboard_ok   "dashboard restored" || fail "dashboard restore verification failed"

echo
echo "[2/8] Recover exact source from known-good deployment"
python3 - "${GOOD_DEPLOYMENT}" "${TEAM_ID}" "${SRC}" <<'PY'
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

deployment, team_id, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)

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
        if isinstance(obj, dict):
            token=str(obj.get("token") or "").strip()
            if token:
                return token
    raise SystemExit("[FAIL] Vercel auth token not found. Log in with: vercel login")

token=find_token()

def get_json(url: str):
    req=urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "kalman-hub-source-recovery/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

q=urllib.parse.urlencode({"teamId": team_id})

# A production "redeploy" can expose the file tree while omitting source
# content for some entries. Follow Vercel's originalDeploymentId chain back
# to the actual uploaded CLI deployment before reading source files.
source_deployment=deployment
seen_deployments=set()
for _ in range(8):
    if source_deployment in seen_deployments:
        raise SystemExit("[FAIL] deployment originalDeploymentId cycle detected")
    seen_deployments.add(source_deployment)

    meta=get_json(
        f"https://api.vercel.com/v13/deployments/{source_deployment}?{q}"
    )
    original=str(((meta.get("meta") or {}).get("originalDeploymentId")) or "").strip()
    if not original or original == source_deployment:
        break
    print(
        f"[INFO] Vercel redeploy source hop: "
        f"{source_deployment} -> {original}"
    )
    source_deployment=original
else:
    raise SystemExit("[FAIL] originalDeploymentId chain too deep")

print(f"[INFO] source deployment: {source_deployment}")

tree=get_json(
    f"https://api.vercel.com/v6/deployments/{source_deployment}/files?{q}"
)
nodes=tree if isinstance(tree, list) else tree.get("files") or tree.get("children") or []

downloaded=[]

def file_payload(uid: str, rel: Path):
    # Primary path for CLI deployments.
    file_q=urllib.parse.urlencode({"teamId": team_id})
    payload=get_json(
        f"https://api.vercel.com/v8/deployments/"
        f"{source_deployment}/files/{uid}?{file_q}"
    )
    if isinstance(payload.get("content"), str):
        return payload

    # Some Vercel deployments only return content when path is supplied.
    # Retry with the exact relative path rather than failing immediately.
    file_q_with_path=urllib.parse.urlencode({
        "teamId": team_id,
        "path": rel.as_posix(),
    })
    retry=get_json(
        f"https://api.vercel.com/v8/deployments/"
        f"{source_deployment}/files/{uid}?{file_q_with_path}"
    )
    if isinstance(retry.get("content"), str):
        return retry

    keys=sorted(set(payload.keys()) | set(retry.keys()))
    raise SystemExit(
        f"[FAIL] no content for {rel} "
        f"(deployment={source_deployment}, response_keys={keys})"
    )

def walk(entries, prefix=Path("")):
    for e in entries or []:
        name=str(e.get("name") or "")
        if not name or name in {".",".."}:
            continue
        rel=prefix / name
        if ".." in rel.parts:
            raise SystemExit(f"[FAIL] unsafe deployment path: {rel}")

        children=e.get("children") or []
        typ=str(e.get("type") or "").lower()
        if typ in {"directory","folder"} or children:
            walk(children, rel)
            continue

        uid=str(e.get("uid") or e.get("id") or "")
        if not uid:
            raise SystemExit(f"[FAIL] missing uid for {rel}")

        payload=file_payload(uid, rel)
        content=payload.get("content")
        encoding=str(payload.get("encoding") or "").lower()

        raw=base64.b64decode(content) if encoding == "base64" else content.encode("utf-8")
        dst=(out_dir / rel).resolve()
        root=out_dir.resolve()
        if root not in dst.parents and dst != root:
            raise SystemExit(f"[FAIL] unsafe output path: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        downloaded.append(rel.as_posix())

walk(nodes)

print(f"[PASS] recovered files={len(downloaded)}")
required={"index.html","app.js","style.css","api/health.js","api/account.js"}
missing=sorted(required-set(downloaded))
if missing:
    raise SystemExit(f"[FAIL] recovered source missing: {missing}")

api_js=[p for p in downloaded if p.startswith("api/") and p.endswith(".js")]
if len(api_js) != 12:
    raise SystemExit(f"[FAIL] expected 12 API functions, recovered {len(api_js)}")

print("[PASS] full 12-function source recovered")
PY

tar -C "${SRC}" -czf "/root/kalman-hub-v749-source-${STAMP}.tar.gz" .
chmod 600 "/root/kalman-hub-v749-source-${STAMP}.tar.gz"
echo "Source backup: /root/kalman-hub-v749-source-${STAMP}.tar.gz"

echo
echo "[3/8] Patch account mapping + KRW reference values"
python3 - "${SRC}" <<'PY'
from __future__ import annotations
from pathlib import Path
import re
import sys

root=Path(sys.argv[1])
app_path=root/"app.js"
css_path=root/"style.css"
index_path=root/"index.html"
health_path=root/"api/health.js"
dashboard_path=root/"api/dashboard.js"

app=app_path.read_text(encoding="utf-8")
css=css_path.read_text(encoding="utf-8")
index=index_path.read_text(encoding="utf-8")
health=health_path.read_text(encoding="utf-8")
dashboard=dashboard_path.read_text(encoding="utf-8")

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f"[FAIL] {label}: expected 1 match, got {count}")
    return text.replace(old,new,1)

# Correct Toss nested holding structures.
app=replace_once(
    app,
    "function evalValue(h){return pick(h,['evaluationAmount','evaluationValue','marketValue','evaluatedAmount','currentValue','amount'])}",
    """function evalValue(h){
  const mv=h?.marketValue;
  if(mv&&typeof mv==='object')return pick(mv,['amountAfterCost','amount']);
  return pick(h,['evaluationAmount','evaluationValue','evaluatedAmount','currentValue','amount']);
}""",
    "marketValue mapping",
)
app=replace_once(
    app,
    "function pnlValue(h){return pick(h,['profitLoss','pnl','evaluationProfitLoss','unrealizedProfitLoss','gainLoss'])}",
    """function pnlValue(h){
  const pl=h?.profitLoss;
  if(pl&&typeof pl==='object')return pick(pl,['amountAfterCost','amount']);
  return pick(h,['pnl','evaluationProfitLoss','unrealizedProfitLoss','gainLoss']);
}""",
    "profitLoss amount mapping",
)
app=replace_once(
    app,
    "function pnlRate(h){return pick(h,['profitRate','pnlRate','returnRate','evaluationProfitRate','gainLossRate'])}",
    """function pnlRate(h){
  const pl=h?.profitLoss;
  if(pl&&typeof pl==='object')return pick(pl,['rateAfterCost','rate']);
  return pick(h,['profitRate','pnlRate','returnRate','evaluationProfitRate','gainLossRate']);
}""",
    "profitLoss rate mapping",
)

anchor="function inferCurrency(h){const c=String(pick(h,['currency','currencyCode'])||'').toUpperCase();return c==='USD'?'USD':'KRW'}\n"
helpers=r"""
const accountUsd2=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2});
const accountUsd4=new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:4});
let accountFxCache=null;
let accountFxCachedAt=0;
function accountUsd(v,d=4){const x=n(v);if(x==null)return '—';return (d===2?accountUsd2:accountUsd4).format(x)}
function accountKrw(v,fx){
  const x=n(v),r=n(fx?.rate);
  if(x==null||r==null)return '원화 환산 —';
  return '≈ '+won.format(x*r);
}
function accountFxLabel(fx){
  const rate=n(fx?.rate);
  if(rate==null)return '원화 환산 실패 · USD 원본값만 표시';
  return `USD/KRW ${fmt(rate,2)} · ${esc(fx.source||'FX')} · 원화는 참고 환산값`;
}
async function loadAccountFx(){
  const now=Date.now();
  if(accountFxCache&&now-accountFxCachedAt<30*60*1000)return accountFxCache;
  const probes=[
    async()=>{
      const r=await fetch('https://open.er-api.com/v6/latest/USD',{cache:'no-store',mode:'cors'});
      if(!r.ok)throw new Error('OPEN_ER_HTTP_'+r.status);
      const j=await r.json(),rate=n(j?.rates?.KRW);
      if(rate==null||rate<=0)throw new Error('OPEN_ER_RATE');
      return {rate,source:'OPEN-ER',as_of:j?.time_last_update_utc||null};
    },
    async()=>{
      const r=await fetch('https://api.frankfurter.dev/v2/rate/usd/krw',{cache:'no-store',mode:'cors'});
      if(!r.ok)throw new Error('FRANKFURTER_HTTP_'+r.status);
      const j=await r.json(),rate=n(j?.rate);
      if(rate==null||rate<=0)throw new Error('FRANKFURTER_RATE');
      return {rate,source:'FRANKFURTER',as_of:j?.date||null};
    }
  ];
  for(const probe of probes){
    try{
      const fx=await probe();
      accountFxCache=fx;accountFxCachedAt=now;
      return fx;
    }catch(_){}
  }
  return null;
}
"""
if anchor not in app:
    raise SystemExit("[FAIL] inferCurrency anchor missing")
app=app.replace(anchor, anchor+helpers, 1)

start=app.find("async function loadAccount(){")
end=app.find("\nfunction barRows(", start)
if start < 0 or end < 0:
    raise SystemExit("[FAIL] loadAccount block missing")

load_account=r"""async function loadAccount(){
  const box=$('#account'),btn=$('#accountRefresh');
  btn.disabled=true;btn.textContent='불러오는 중';
  box.innerHTML='<div class="muted">계좌를 불러오는 중...</div>';
  try{
    const [j,fx]=await Promise.all([getJSON('/api/account'),loadAccountFx()]);
    const accounts=asArray(j.accounts),holdings=asArray(j.holdings);
    const usdPower=pick(unwrap(j.buying_power_usd),['cashBuyingPower','buyingPower','availableAmount','available','amount','value']);
    const krwPower=pick(unwrap(j.buying_power_krw),['cashBuyingPower','buyingPower','availableAmount','available','amount','value']);
    const hroot=unwrap(j.holdings)||{};

    const totalPurchaseUsd=n(hroot?.totalPurchaseAmount?.usd);
    const totalEvalUsd=n(hroot?.marketValue?.amountAfterCost?.usd??hroot?.marketValue?.amount?.usd);
    const totalPnlUsd=n(hroot?.profitLoss?.amountAfterCost?.usd??hroot?.profitLoss?.amount?.usd);
    const calculatedTotalRate=(
      totalPurchaseUsd!=null&&totalPurchaseUsd!==0&&totalPnlUsd!=null
        ? totalPnlUsd/totalPurchaseUsd
        : null
    );

    const summary=[
      card('총 매입금액',accountUsd(totalPurchaseUsd),accountKrw(totalPurchaseUsd,fx)),
      card('총 평가금액',accountUsd(totalEvalUsd),accountKrw(totalEvalUsd,fx)),
      card(
        '평가손익',
        accountUsd(totalPnlUsd),
        `${accountKrw(totalPnlUsd,fx)} · 합계수익률 ${calculatedTotalRate==null?'—':pct(calculatedTotalRate,100)}`
      ),
      card('매수가능',money(krwPower,'KRW'),`USD ${accountUsd(usdPower,2)}`)
    ].join('');

    const rows=holdings.slice(0,20).map(h=>{
      const cur=inferCurrency(h),pnl=pnlValue(h),rate=pnlRate(h),pv=n(pnl);
      const pnlClass=pv==null?'':pv>0?'good':pv<0?'bad':'';
      const purchase=pick(h?.marketValue||{},['purchaseAmount']);
      const market=evalValue(h);
      const last=pick(h,['lastPrice']);
      const avg=pick(h,['averagePurchasePrice']);

      if(cur==='USD'){
        return `<div class="holding account-holding">
          <div class="holding-head">
            <div>
              <div class="name">${esc(holdingName(h))} <span class="small">${esc(holdingSub(h))}</span></div>
              <div class="small">보유 ${fmt(qty(h),6)}주</div>
            </div>
            <div class="right account-price">
              <div>현재가 <b>${accountUsd(last,2)}</b></div>
              <div class="small">${accountKrw(last,fx)}</div>
              <div class="small">평단 ${accountUsd(avg,2)} · ${accountKrw(avg,fx)}</div>
            </div>
          </div>
          <div class="holding-metrics">
            <div class="holding-metric">
              <span>매입금액</span><b>${accountUsd(purchase)}</b><small>${accountKrw(purchase,fx)}</small>
            </div>
            <div class="holding-metric">
              <span>평가금액</span><b>${accountUsd(market)}</b><small>${accountKrw(market,fx)}</small>
            </div>
            <div class="holding-metric ${pnlClass}">
              <span>평가손익</span><b>${accountUsd(pnl)}</b><small>${accountKrw(pnl,fx)} · ${rate!=null?pct(rate,100):'—'}</small>
            </div>
          </div>
        </div>`;
      }

      return `<div class="holding account-holding">
        <div class="holding-head">
          <div><div class="name">${esc(holdingName(h))} <span class="small">${esc(holdingSub(h))}</span></div><div class="small">보유 ${fmt(qty(h),6)}주</div></div>
          <div class="right account-price"><div>현재가 <b>${money(last,'KRW')}</b></div><div class="small">평단 ${money(avg,'KRW')}</div></div>
        </div>
        <div class="holding-metrics">
          <div class="holding-metric"><span>매입금액</span><b>${money(purchase,'KRW')}</b></div>
          <div class="holding-metric"><span>평가금액</span><b>${money(market,'KRW')}</b></div>
          <div class="holding-metric ${pnlClass}"><span>평가손익</span><b>${money(pnl,'KRW')}</b><small>${rate!=null?pct(rate,100):'—'}</small></div>
        </div>
      </div>`;
    }).join('');

    box.innerHTML=`<div class="account-summary grid4">${summary}</div>
      <div class="statusline">${badge('연결됨','ok')}<span class="muted">계좌 ${accounts.length||1} · 보유 ${holdings.length}종목 · ${time(j.generated_at)}</span></div>
      <div class="statusline"><span class="small">${accountFxLabel(fx)}</span></div>
      <div class="holdings">${rows||'<div class="notice">현재 표시할 보유종목이 없습니다.</div>'}</div>`;
  }catch(e){
    const cfg=e?.payload?.error==='ACCOUNT_GATEWAY_NOT_CONFIGURED';
    box.innerHTML=`<div class="notice ${cfg?'':'error'}"><b>${cfg?'계좌 연결 준비됨':'계좌를 불러오지 못했습니다.'}</b><div class="small" style="margin-top:5px">${cfg?'고정 IP Toss Gateway 연결값이 Production 환경에 필요합니다.':'서버 Gateway 상태와 읽기 전용 인증을 확인하세요.'}</div></div>`;
  }finally{btn.disabled=false;btn.textContent='새로고침'}
}
"""
app=app[:start]+load_account+app[end:]

render_anchor="""function renderMarket(m,j){
  if(m==='GLOBAL')return renderGlobal(j);if(m==='CRYPTO')return renderCrypto(j);if(m==='US')return renderUS(j);return renderKR(j)
}
"""
render_shadow=r"""function renderShadow(j){
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
app=replace_once(app, render_anchor, render_shadow, "renderMarket SHADOW")

shadow_proxy=r"""
  const __kalmanUrl = new URL(req.url || '/api/dashboard', 'http://localhost');
  if ((__kalmanUrl.searchParams.get('market') || '').toUpperCase() === 'SHADOW') {
    const shadowUrl = 'https://kalman-shadow-readonly.vercel.app/api/shadow';
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    try {
      const upstream = await fetch(shadowUrl, {
        method: 'GET',
        headers: {'Accept': 'application/json'},
        cache: 'no-store'
      });
      const body = await upstream.text();
      res.setHeader('X-Kalman-Shadow-Source', 'standalone-snapshot');
      res.statusCode = upstream.status;
      res.end(body);
      return;
    } catch (err) {
      const code = String(err?.cause?.code || err?.code || err?.name || 'SHADOW_SNAPSHOT_FETCH_ERROR');
      res.statusCode = 502;
      res.end(JSON.stringify({error:'SHADOW_SNAPSHOT_FETCH_FAILED', code}));
      return;
    }
  }
"""

handler_patterns=[
    r"(export\s+default\s+async\s+function(?:\s+\w+)?\s*\(\s*req\s*,\s*res\s*\)\s*\{)",
    r"(module\.exports\s*=\s*async\s+function(?:\s+\w+)?\s*\(\s*req\s*,\s*res\s*\)\s*\{)",
    r"(module\.exports\s*=\s*async\s*\(\s*req\s*,\s*res\s*\)\s*=>\s*\{)",
]
patched=False
for pattern in handler_patterns:
    dashboard,n=re.subn(
        pattern,
        lambda m: m.group(1)+"\n"+shadow_proxy,
        dashboard,
        count=1,
    )
    if n==1:
        patched=True
        break
if not patched:
    raise SystemExit("[FAIL] api/dashboard.js handler anchor not recognized")

css += r"""
.account-holding{display:block;padding:13px 0}
.holding-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.account-price{min-width:220px}
.holding-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:9px}
.holding-metric{background:#0e1729;border:1px solid #26324d;border-radius:10px;padding:9px;display:flex;flex-direction:column;gap:2px}
.holding-metric>span{font-size:10px;color:#8fa0bd}
.holding-metric>b{font-size:14px}
.holding-metric>small{font-size:10px;color:#94a3b8}
.holding-metric.good small,.holding-metric.good b{color:var(--good)}
.holding-metric.bad small,.holding-metric.bad b{color:var(--bad)}
@media(max-width:760px){
  .account-holding{display:block}
  .holding-head{display:block}
  .holding-head>.right{text-align:left;margin-top:7px}
  .account-price{min-width:0}
  .holding-metrics{grid-template-columns:1fr}
}
"""

if "vNext.7.4.9" not in index:
    raise SystemExit("[FAIL] index version marker missing")

kr_tab='<button class="tab" data-m="KR">한국장</button>'
if index.count(kr_tab) != 1:
    raise SystemExit("[FAIL] KR tab anchor missing")
index=index.replace(
    kr_tab,
    kr_tab+'\n      <button class="tab" data-m="SHADOW">Shadow</button>',
    1,
)

index=index.replace(
    "vNext.7.4.9 · MA20/60 + Actual Model Performance Tabs",
    "vNext.7.4.11 · Account + Forward SHADOW Read Only",
    1,
)

# Health metadata only; contracts/model/risk logic are untouched.
health=health.replace("vNext.7.4.9","vNext.7.4.11")

# Static safety checks.
assert "const mv=h?.marketValue" in app
assert "const pl=h?.profitLoss" in app
assert "fmt(qty(h),6)" in app
assert "accountKrw" in app
assert "pct(rate,100)" in app
assert "calculatedTotalRate" in app
assert "open.er-api.com" in app
assert "api.frankfurter.dev/v2/rate/usd/krw" in app
assert "function renderShadow(j)" in app
assert 'data-m="SHADOW"' in index
assert "kalman-shadow-readonly.vercel.app/api/shadow" in dashboard
assert "run_model_v2" not in app
assert "vNext.7.4.11" in index

for p in list((root/"api").rglob("*.js")) + list((root/"lib").rglob("*.js")):
    t=p.read_text(encoding="utf-8")
    if "req.query" in t or "url.parse(" in t:
        raise SystemExit(f"[FAIL] query-parser regression token in {p.relative_to(root)}")

api_count=len(list((root/"api").rglob("*.js")))
if api_count != 12:
    raise SystemExit(f"[FAIL] function count changed: {api_count}")

app_path.write_text(app, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")
index_path.write_text(index, encoding="utf-8")
health_path.write_text(health, encoding="utf-8")
dashboard_path.write_text(dashboard, encoding="utf-8")

print("[PASS] account UI + SHADOW read-only patched")
print("[PASS] API function count = 12")
print("[PASS] query-parser regression scan")
PY

echo
echo "[4/8] Link recovered source to existing Vercel project"
cd "${SRC}"
mkdir -p .vercel
cat > .vercel/project.json <<EOF
{"projectId":"${PROJECT_ID}","orgId":"${TEAM_ID}"}
EOF

# Verify which files would be uploaded.
vercel deploy --dry --format=json --scope "${TEAM_SLUG}" >"${WORK}/dry-run.json"
python3 - "${WORK}/dry-run.json" <<'PY'
import json, sys
from pathlib import Path
raw=Path(sys.argv[1]).read_text(encoding="utf-8",errors="replace").strip()
if not raw:
    raise SystemExit("[FAIL] empty Vercel dry-run output")
try:
    json.loads(raw)
except Exception:
    # Some CLI releases prepend/append informational text even with --format=json.
    # The dry-run command already exited 0; keep the artifact for audit instead
    # of failing solely on presentation formatting.
    print("[WARN] Vercel dry-run output is not pure JSON; command exit was successful")
else:
    print("[PASS] Vercel dry-run manifest JSON")
PY

echo
echo "[5/8] Build production-environment candidate WITHOUT domain assignment"
set +e
vercel deploy   --prod   --skip-domain   --yes   --scope "${TEAM_SLUG}"   2>&1 | tee "${WORK}/candidate-deploy.log"
DEPLOY_RC=${PIPESTATUS[0]}
set -e

[ "${DEPLOY_RC}" -eq 0 ] || fail "candidate deployment failed"

CANDIDATE="$(
  python3 - "${WORK}/candidate-deploy.log" <<'PY'
import re,sys
s=open(sys.argv[1], encoding="utf-8", errors="replace").read()
urls=re.findall(r'https://[A-Za-z0-9.-]+\.vercel\.app', s)
print(urls[-1] if urls else "")
PY
)"
[ -n "${CANDIDATE}" ] || fail "candidate URL not found"
echo "Candidate: ${CANDIDATE}"

echo
echo "[6/8] Candidate smoke tests"

vcurl() {
  local path="$1"
  local out="$2"
  vercel curl "${CANDIDATE}${path}" -- --silent --show-error >"${out}"
}

vcurl "/api/health" "${WORK}/candidate-health.json"
python3 - "${WORK}/candidate-health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert x.get("investment_hub_version") == "vNext.7.4.11", x.get("investment_hub_version")
assert x.get("account_gateway_configured") is True
assert x.get("account_gateway_secret_configured") is True
assert x.get("account_trade_execution") is False
assert x.get("trade_enabled") is False
routes=x.get("required_routes") or []
for r in ("/api/account","/api/dashboard","/api/history"):
    assert r in routes, r
print("[PASS] candidate health")
PY

vcurl "/api/account" "${WORK}/candidate-account.json"
python3 - "${WORK}/candidate-account.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert x.get("status")=="READY"
assert x.get("trade_execution") is False
parts=x.get("parts") or {}
for k in ("accounts","holdings","buying_power_usd","buying_power_krw"):
    assert (parts.get(k) or {}).get("ok") is True, (k,parts.get(k))
h=((x.get("holdings") or {}).get("result") or {})
items=h.get("items") or []
assert items
for item in items:
    assert isinstance(item.get("marketValue"),dict)
    assert isinstance(item.get("profitLoss"),dict)
    assert item["marketValue"].get("amount") is not None
    assert item["profitLoss"].get("amount") is not None
print(f"[PASS] candidate account / holdings={len(items)}")
PY

vcurl "/api/dashboard?market=GLOBAL" "${WORK}/candidate-dashboard.json"
python3 - "${WORK}/candidate-dashboard.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert not x.get("error"), x
assert x.get("payload") is not None
print("[PASS] candidate dashboard")
PY

vcurl "/api/dashboard?market=SHADOW" "${WORK}/candidate-shadow.json"
python3 - "${WORK}/candidate-shadow.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert x.get("status")=="READY", x
assert x.get("schema_version")=="kalman-shadow-readonly-v1", x
inv=x.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
for market in ("US","KR","BTC"):
    assert market in (x.get("signals") or {}), market
print("[PASS] candidate SHADOW read-only")
PY

vcurl "/api/history?asset=BTC&count=2" "${WORK}/candidate-history.json"
python3 - "${WORK}/candidate-history.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert not x.get("error"), x
print("[PASS] candidate history")
PY

vercel curl "${CANDIDATE}/app.js" -- --silent --show-error >"${WORK}/candidate-app.js"
grep -q "accountKrw" "${WORK}/candidate-app.js" || fail "candidate app.js lacks KRW mapping"
grep -q "fmt(qty(h),6)" "${WORK}/candidate-app.js" || fail "candidate app.js lacks fractional quantity precision"
grep -q "renderShadow" "${WORK}/candidate-app.js" || fail "candidate app.js lacks SHADOW read-only renderer"
echo "[PASS] candidate UI bundle"

echo
echo "[7/8] Promote verified candidate to production"
vercel promote "${CANDIDATE}" --yes --scope "${TEAM_SLUG}" >/dev/null

rollback() {
  echo "[ROLLBACK] restoring known-good production" >&2
  vercel promote "${GOOD_URL}" --yes --scope "${TEAM_SLUG}" >/dev/null || true
}

prod_health_ok() {
  local file="$1"
  python3 - "$file" <<'PY' >/dev/null 2>&1
import json,sys
from pathlib import Path
try:
    x=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
except Exception:
    raise SystemExit(1)
ok=(
    x.get("investment_hub_version")=="vNext.7.4.11"
    and x.get("account_gateway_configured") is True
    and x.get("account_gateway_secret_configured") is True
    and x.get("account_trade_execution") is False
    and x.get("trade_enabled") is False
)
raise SystemExit(0 if ok else 1)
PY
}

PROD_READY=false
for _ in $(seq 1 45); do
  : >"${WORK}/prod-health.json"
  curl -fsS --max-time 10 "${PROD_URL}/api/health"     >"${WORK}/prod-health.json" 2>/dev/null || true
  if prod_health_ok "${WORK}/prod-health.json"; then
    PROD_READY=true
    break
  fi
  sleep 2
done

if [ "${PROD_READY}" != true ]; then
  rollback
  fail "production health failed after promotion"
fi
echo "[PASS] production vNext.7.4.11 health"

if ! wait_json_route   "${PROD_URL}/api/account"   "${WORK}/prod-account.json"   account_ok   "production account READY"; then
  rollback
  fail "production account smoke failed"
fi

if ! wait_json_route   "${PROD_URL}/api/dashboard?market=GLOBAL"   "${WORK}/prod-dashboard.json"   dashboard_ok   "production dashboard READY"; then
  rollback
  fail "production dashboard smoke failed"
fi

shadow_ok() {
  local file="$1"
  python3 - "$file" <<'PY' >/dev/null 2>&1
import json,sys
from pathlib import Path
try:
    x=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8").strip())
except Exception:
    raise SystemExit(1)
inv=x.get("invariants") or {}
ok=(
    x.get("status")=="READY"
    and x.get("schema_version")=="kalman-shadow-readonly-v1"
    and inv.get("read_only") is True
    and inv.get("trade_execution") is False
    and all(k in (x.get("signals") or {}) for k in ("US","KR","BTC"))
)
raise SystemExit(0 if ok else 1)
PY
}

if ! wait_json_route   "${PROD_URL}/api/dashboard?market=SHADOW"   "${WORK}/prod-shadow.json"   shadow_ok   "production SHADOW read-only READY"; then
  rollback
  fail "production SHADOW read-only smoke failed"
fi

APP_READY=false
for _ in $(seq 1 30); do
  : >"${WORK}/prod-app.js"
  curl -fsS --max-time 20 "${PROD_URL}/app.js" >"${WORK}/prod-app.js" 2>/dev/null || true
  if grep -q "accountKrw" "${WORK}/prod-app.js"      && grep -q "fmt(qty(h),6)" "${WORK}/prod-app.js"      && grep -q "renderShadow" "${WORK}/prod-app.js"; then
    APP_READY=true
    break
  fi
  sleep 2
done

if [ "${APP_READY}" != true ]; then
  rollback
  fail "production UI marker missing"
fi

echo "[PASS] production account + dashboard + SHADOW read-only + UI"

echo
echo "[8/8] Gateway live-trading gate verification"
curl -fsS --max-time 5 http://127.0.0.1:8787/health >"${WORK}/gateway-health.json"
python3 - "${WORK}/gateway-health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert x.get("status")=="ok"
assert x.get("tradingEnabled") is False
assert x.get("liveGateOpen") is False
print("[PASS] automated gateway trading remains OFF")
print("[INFO] manualTradingEnabled=", x.get("manualTradingEnabled"))
print("[INFO] manualLiveGateOpen=", x.get("manualLiveGateOpen"))
PY

echo
echo "=================================================="
echo "PRODUCTION COMPLETE"
echo "=================================================="
echo "URL: ${PROD_URL}"
echo "Version: vNext.7.4.11"
echo "Account: Toss USD originals + KRW reference conversion"
echo "FX: browser-side OPEN-ER -> Frankfurter fallback"
echo "API functions: 12"
echo "SHADOW web: READ ONLY"
echo "Automated trade execution: OFF"
echo "Manual trade gate: managed separately by configure_manual_live_trading_env.sh"
echo "Recovered source backup:"
echo "  /root/kalman-hub-v749-source-${STAMP}.tar.gz"
echo "Work log:"
echo "  ${WORK}"
echo "=================================================="
