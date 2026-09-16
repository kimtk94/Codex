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
GOOD_DEPLOYMENT="${KALMAN_HUB_GOOD_DEPLOYMENT:-dpl_HgCwwzpNyaWagXseBBetpb3zTcxf}"
GOOD_URL="${KALMAN_HUB_GOOD_URL:-https://kalman-investment-hub-v2-a32curmrp-insk1285-9320s-projects.vercel.app}"

STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="/tmp/kalman-hub-v7418-${STAMP}"
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
echo "Kalman Investment Hub vNext.7.4.18"
echo "Account + actual-model B/S + SHADOW read-only"
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
    x.get("investment_hub_version") in {"vNext.7.4.17","vNext.7.4.18"}
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
  echo "[PASS] healthy vNext.7.4.14+ full production already active; promotion skipped"
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
    and isinstance(x.get("trade_execution"), bool)
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
import shutil
import sys
import urllib.error
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
skipped_non_files=[]

def normalize_file_payload(payload):
    """Normalize Vercel deployment-file response variants.

    Documented responses expose base64 source as `content`, but some current
    API responses wrap the body in a top-level `data` field. Support both
    without logging source contents.
    """
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("content"), str):
        return {
            "content": payload["content"],
            "encoding": payload.get("encoding") or "base64",
        }

    data=payload.get("data")

    if isinstance(data, dict):
        if isinstance(data.get("content"), str):
            return {
                "content": data["content"],
                "encoding": data.get("encoding") or payload.get("encoding") or "base64",
            }
        if isinstance(data.get("data"), str):
            return {
                "content": data["data"],
                "encoding": data.get("encoding") or payload.get("encoding") or "base64",
            }

    if isinstance(data, str):
        return {
            "content": data,
            # Vercel's deployment-file endpoint returns file bytes encoded as
            # base64. If a deployment returns plain text despite that contract,
            # the decode helper below safely falls back to UTF-8.
            "encoding": payload.get("encoding") or "base64-or-text",
        }

    return None


def decode_file_payload(normalized, rel: Path):
    content=normalized["content"]
    encoding=str(normalized.get("encoding") or "").lower()

    if encoding == "base64":
        try:
            return base64.b64decode(content, validate=True)
        except Exception as exc:
            raise SystemExit(
                f"[FAIL] invalid base64 content for {rel}: {exc}"
            )

    if encoding == "base64-or-text":
        compact="".join(content.split())
        try:
            return base64.b64decode(compact, validate=True)
        except Exception:
            return content.encode("utf-8")

    return content.encode("utf-8")


def file_payload(uid: str, rel: Path):
    # Primary path for CLI deployments.
    file_q=urllib.parse.urlencode({"teamId": team_id})
    try:
        payload=get_json(
            f"https://api.vercel.com/v8/deployments/"
            f"{source_deployment}/files/{uid}?{file_q}"
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                f"[FAIL] source file 404 for {rel} "
                f"(deployment={source_deployment}, uid={uid})"
            )
        raise
    normalized=normalize_file_payload(payload)
    if normalized is not None:
        return normalized

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
    normalized=normalize_file_payload(retry)
    if normalized is not None:
        return normalized

    keys=sorted(set(payload.keys()) | set(retry.keys()))
    data_type=type(payload.get("data")).__name__
    retry_data_type=type(retry.get("data")).__name__
    raise SystemExit(
        f"[FAIL] no source bytes for {rel} "
        f"(deployment={source_deployment}, response_keys={keys}, "
        f"data_types={data_type}/{retry_data_type})"
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

        if typ in {"directory","folder"}:
            walk(children, rel)
            continue

        # Vercel documents uid as valid only for type=file.
        # Lambda/middleware/symlink/invalid entries are deployment artifacts,
        # not downloadable source files.
        if typ != "file":
            skipped_non_files.append((rel.as_posix(), typ or "unknown"))
            continue

        uid=str(e.get("uid") or "")
        if not uid:
            raise SystemExit(f"[FAIL] missing file uid for {rel}")

        payload=file_payload(uid, rel)
        raw=decode_file_payload(payload, rel)
        dst=(out_dir / rel).resolve()
        root=out_dir.resolve()
        if root not in dst.parents and dst != root:
            raise SystemExit(f"[FAIL] unsafe output path: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        downloaded.append(rel.as_posix())

walk(nodes)

if skipped_non_files:
    counts={}
    for _, typ in skipped_non_files:
        counts[typ]=counts.get(typ, 0)+1
    print(
        "[INFO] skipped non-source FileTree entries:",
        ", ".join(f"{k}={v}" for k,v in sorted(counts.items()))
    )

print(f"[PASS] recovered files={len(downloaded)}")

required={"index.html","app.js","style.css","api/health.js","vercel.json"}

def normalize_source_root() -> None:
    global downloaded

    current=set(downloaded)
    if required.issubset(current):
        return

    # Vercel's recovered deployment tree can preserve the original upload
    # directory (for this project: src/). Detect a single common source prefix
    # containing the complete app and flatten it into out_dir so the rest of
    # the deployment script can keep using the known-good root layout.
    prefixes=[]
    for candidate in ("src","app","web","site"):
        prefixed={f"{candidate}/{p}" for p in required}
        if prefixed.issubset(current):
            prefixes.append(candidate)

    if len(prefixes) != 1:
        sample=", ".join(sorted(downloaded)[:40])
        missing=sorted(required-current)
        raise SystemExit(
            f"[FAIL] recovered source missing: {missing}; "
            f"prefix_candidates={prefixes}; recovered_sample=[{sample}]"
        )

    prefix=prefixes[0]
    source_dir=(out_dir / prefix).resolve()
    if out_dir.resolve() not in source_dir.parents:
        raise SystemExit(f"[FAIL] unsafe source prefix: {source_dir}")

    moved=[]
    for src in sorted(source_dir.rglob("*")):
        if not src.is_file():
            continue
        rel=src.relative_to(source_dir)
        dst=(out_dir / rel).resolve()
        if out_dir.resolve() not in dst.parents:
            raise SystemExit(f"[FAIL] unsafe normalized path: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        moved.append(rel.as_posix())

    # Remove the wrapper after normalization so Vercel sees one canonical
    # project root only. This avoids duplicate src/api vs api discovery and
    # guarantees that the patch stage and deploy stage operate on the same files.
    shutil.rmtree(source_dir)

    downloaded=sorted(set(downloaded) | set(moved))
    print(
        f"[INFO] normalized recovered source root: "
        f"{prefix}/ -> ./ ({len(moved)} files; wrapper removed)"
    )

normalize_source_root()

current=set(downloaded)
missing=sorted(required-current)
if missing:
    raise SystemExit(f"[FAIL] recovered source missing after normalization: {missing}")

api_js=[p for p in current if p.startswith("api/") and p.endswith(".js")]
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
vercel_path=root/"vercel.json"

def resolve_api_route(route: str) -> Path:
    """Resolve an external /api/... route to its actual source function.

    This deployment intentionally exposes more public routes than physical
    serverless source files by using vercel.json rewrites/routes. Preserve that
    12-function architecture instead of requiring one file per public route.
    """
    import json
    cfg=json.loads(vercel_path.read_text(encoding="utf-8"))

    candidates=[]

    # Modern Vercel rewrites: {"source":"/api/dashboard","destination":"/api/market"}
    rewrites=cfg.get("rewrites") or []
    if isinstance(rewrites, dict):
        rewrites=[rewrites]
    for item in rewrites:
        if not isinstance(item, dict):
            continue
        src=str(item.get("source") or "")
        dst=str(item.get("destination") or "")
        if src == route and dst:
            candidates.append(dst)

    # Legacy routes: {"src":"^/api/dashboard$","dest":"/api/market"}
    for item in cfg.get("routes") or []:
        if not isinstance(item, dict):
            continue
        src=str(item.get("src") or "")
        dst=str(item.get("dest") or item.get("destination") or "")
        normalized=src.replace("^","").replace("$","")
        if normalized == route and dst:
            candidates.append(dst)

    # A physical file is also valid when no rewrite is needed.
    direct=root/(route.lstrip("/")+".js")
    if direct.exists():
        return direct

    for dst in candidates:
        clean=dst.split("?",1)[0].lstrip("/")
        p=root/(clean if clean.endswith(".js") else clean+".js")
        if p.exists():
            print(f"[INFO] route {route} -> {p.relative_to(root)}")
            return p

    raise SystemExit(
        f"[FAIL] cannot resolve {route} from vercel.json; candidates={candidates}"
    )

dashboard_path=resolve_api_route("/api/dashboard")

app=app_path.read_text(encoding="utf-8")
css=css_path.read_text(encoding="utf-8")
index=index_path.read_text(encoding="utf-8")
health=health_path.read_text(encoding="utf-8")
dashboard=dashboard_path.read_text(encoding="utf-8")

# vNext.7.4.18 adds a static US Universe ranking page.
if "vNext.7.4.17" in index and "NEXT ACTIONS" in index:
    import os
    import subprocess
    patcher=Path(
        os.environ.get("KALMAN_APP_ROOT","/opt/kalman/app")
    )/"scripts/patch_investment_hub_v7418.py"
    if not patcher.exists():
        raise SystemExit(f"[FAIL] v7.4.18 patcher missing: {patcher}")
    subprocess.run([sys.executable,str(patcher),str(root)],check=True)
    sys.exit(0)

# vNext.7.4.17 adds execution-aware NEXT ACTIONS display.
if "vNext.7.4.16" in index and "Investment Intelligence" in index:
    import os
    import subprocess
    patcher=Path(
        os.environ.get("KALMAN_APP_ROOT","/opt/kalman/app")
    )/"scripts/patch_investment_hub_v7417.py"
    if not patcher.exists():
        raise SystemExit(f"[FAIL] v7.4.17 patcher missing: {patcher}")
    subprocess.run([sys.executable,str(patcher),str(root)],check=True)
    sys.exit(0)

# vNext.7.4.16 redesigns information hierarchy only.
if "vNext.7.4.15" in index and "R5.1 2026 Annual Ledger" in app:
    import os
    import subprocess
    patcher=Path(
        os.environ.get("KALMAN_APP_ROOT","/opt/kalman/app")
    )/"scripts/patch_investment_hub_v7416.py"
    if not patcher.exists():
        raise SystemExit(f"[FAIL] v7.4.16 patcher missing: {patcher}")
    subprocess.run([sys.executable,str(patcher),str(root)],check=True)
    sys.exit(0)

# vNext.7.4.15 is a display-only delta over verified vNext.7.4.14.
# It exposes the full annual ledger from January instead of recent-only rows.
if "vNext.7.4.14" in index and "R5.1 2026 Annual Ledger" in app:
    import os
    import subprocess
    patcher=Path(
        os.environ.get("KALMAN_APP_ROOT","/opt/kalman/app")
    )/"scripts/patch_investment_hub_v7415.py"
    if not patcher.exists():
        raise SystemExit(f"[FAIL] v7.4.15 patcher missing: {patcher}")
    subprocess.run([sys.executable,str(patcher),str(root)],check=True)
    sys.exit(0)

# vNext.7.4.14 is a small UI delta over the verified vNext.7.4.13 source.
# Keep it in a standalone patcher so the older recovery patches remain frozen.
if "vNext.7.4.13" in index and "R5.1 Forward SHADOW lifecycle" in app:
    import os
    import subprocess
    patcher=Path(
        os.environ.get("KALMAN_APP_ROOT","/opt/kalman/app")
    )/"scripts/patch_investment_hub_v7414.py"
    if not patcher.exists():
        raise SystemExit(f"[FAIL] v7.4.14 patcher missing: {patcher}")
    subprocess.run([sys.executable,str(patcher),str(root)],check=True)
    sys.exit(0)

# vNext.7.4.13 delta: the recovered base is the verified vNext.7.4.12 bundle.
# Only add the persisted R5.1 Forward SHADOW lifecycle UI and metadata.
if "vNext.7.4.12" in index and "STRICT_TOP3_ACTUAL_LEDGER" in app and "accountKrw" in app:
    def delta_replace(text: str, old: str, new: str, label: str) -> str:
        count=text.count(old)
        if count != 1:
            raise SystemExit(f"[FAIL] v7.4.13 {label}: expected 1 match, got {count}")
        return text.replace(old,new,1)

    old_chart=r"""async function usShadowSignalChart(marketSnapshot){
  const selector=marketSnapshot?.payload?.source_payload?.today_selector||{};
  const symbol=String(selector.selected_symbol||'').toUpperCase();
  if(!symbol)return '<div class="notice">현재 표시 가능한 R5.1 모델 신호가 없습니다.</div>';
  const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbol));
  const raw=(hist.items||[]).find(x=>String(x.symbol||'').toUpperCase()===symbol);
  if(!raw)return '<div class="notice">현재 모델 선택 종목의 가격 이력이 없습니다.</div>';
  const events=[];
  if(selector.shadow_entry_this_signal===true){
    events.push({time:selector.as_of_utc,price:n(selector.reference_price),signal:'BUY',event_type:'R5_1_SHADOW_ENTRY',source:'R5.1_SHADOW_SIGNAL'});
  }
  const item={...raw,events,summary:{...(raw.summary||{}),strategy_return_pct:null,closed_trades:0,win_rate_pct:null,open_position:null,rule:'R5.1 SHADOW SIGNAL'}};
  return '<div class="section"><div class="section-title"><h3>현재 R5.1 모델 신호</h3><span class="small">SHADOW · 체결 아님</span></div>'+ytdPointChart(item,{name:symbol,actualModel:true,signalOnly:true,rule:'R5.1 SHADOW'})+'</div>';
}"""

    new_chart=r"""async function usShadowSignalChart(marketSnapshot){
  const src=marketSnapshot?.payload?.source_payload||{};
  const ledger=src.r5_shadow_ledger||{};
  const trades=Array.isArray(ledger.trades)?ledger.trades:[];
  const ledgerEvents=Array.isArray(ledger.events)?ledger.events:[];

  if(trades.length){
    const symbols=[...new Set(trades.map(t=>String(t.symbol||'').toUpperCase()).filter(Boolean))];
    const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbols.join(',')));
    const by=new Map((hist.items||[]).map(x=>[String(x.symbol||'').toUpperCase(),x]));

    const charts=symbols.map(symbol=>{
      const raw=by.get(symbol);
      if(!raw)return '';
      const events=ledgerEvents
        .filter(e=>String(e.symbol||'').toUpperCase()===symbol)
        .map(e=>({...e,price:n(e.price)}))
        .filter(e=>e.price!=null)
        .sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
      const symTrades=trades.filter(t=>String(t.symbol||'').toUpperCase()===symbol);
      const closed=symTrades.filter(t=>t.exit_time&&n(t.return_pct)!=null);
      let multiple=closed.reduce((m,t)=>m*(1+n(t.return_pct)),1);
      const open=symTrades.find(t=>!t.exit_time);
      const rows=raw.rows||[];
      const last=n(rows.at(-1)?.close);
      let openPosition=null;
      if(open&&last!=null&&n(open.entry_price)>0){
        const r=last/n(open.entry_price)-1;
        multiple*=1+r;
        openPosition={
          entry_time:open.entry_time,
          entry_price:n(open.entry_price),
          current_price:last,
          return_pct:r*100
        };
      }
      const wins=closed.filter(t=>n(t.return_pct)>0).length;
      const item={
        ...raw,
        events,
        source:'R5_1_SHADOW_LEDGER',
        summary:{
          ...(raw.summary||{}),
          strategy_return_pct:(multiple-1)*100,
          closed_trades:closed.length,
          win_rate_pct:closed.length?wins/closed.length*100:null,
          open_position:openPosition,
          rule:'R5.1 SHADOW LIFECYCLE'
        }
      };
      return ytdPointChart(item,{name:symbol,actualModel:true,lifecycle:true,rule:'R5.1 SHADOW'});
    }).filter(Boolean).join('');

    return '<div class="section"><div class="section-title"><h3>R5.1 Forward SHADOW lifecycle</h3><span class="small">ledger B/S · 실제 체결 아님</span></div><div class="trade-chart-grid">'+(charts||'<div class="notice">가격 이력을 불러오지 못했습니다.</div>')+'</div></div>';
  }

  const selector=src.today_selector||{};
  const symbol=String(selector.selected_symbol||'').toUpperCase();
  if(!symbol)return '<div class="notice">현재 표시 가능한 R5.1 모델 신호가 없습니다.</div>';
  const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbol));
  const raw=(hist.items||[]).find(x=>String(x.symbol||'').toUpperCase()===symbol);
  if(!raw)return '<div class="notice">현재 모델 선택 종목의 가격 이력이 없습니다.</div>';
  const events=[];
  if(selector.shadow_entry_this_signal===true){
    events.push({time:selector.as_of_utc,price:n(selector.reference_price),signal:'BUY',event_type:'R5_1_SHADOW_ENTRY',source:'R5.1_SHADOW_SIGNAL'});
  }
  const item={...raw,events,summary:{...(raw.summary||{}),strategy_return_pct:null,closed_trades:0,win_rate_pct:null,open_position:null,rule:'R5.1 SHADOW SIGNAL'}};
  return '<div class="section"><div class="section-title"><h3>현재 R5.1 모델 신호</h3><span class="small">SHADOW · 체결 아님</span></div>'+ytdPointChart(item,{name:symbol,actualModel:true,signalOnly:true,rule:'R5.1 SHADOW'})+'</div>';
}"""
    app=delta_replace(app,old_chart,new_chart,"US lifecycle chart")

    old_view=r"""function usModelPerformanceView(j){
  const s=j.summary||{},official=n(s.selector_observed_hit_rate_pct);
  return `<div class="model-disclosure"><b>R5.1 실제 모델 · SHADOW</b><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('R5.1 YTD 수익률','미산출','연속 outcome/체결 ledger 없음')}${card('공식 관측 적중률',official==null?'—':`${official.toFixed(1)}%`,`${fmt(s.selector_prospective_outcomes,0)}개 prospective outcome`)}${card('관측 일수',fmt(s.prospective_distinct_days,0),`${fmt(s.distinct_model_snapshots,0)}개 model snapshot`)}${card('Shadow 신호',fmt(s.shadow_signal_count,0),`${time(s.window_start)} ~ ${time(s.window_end)}`)}</div><div class="notice model-note">현재 R5.1은 frozen prospective / shadow 단계이며 실제 체결 ledger가 없습니다. DB의 60m 가격도 연속봉이 아니라 pipeline snapshot이므로 임의로 +4 bars 수익률을 재구성하지 않습니다. 따라서 이 탭은 현재 공식 prospective <b>적중률·outcome 수·관측기간</b>만 표시하고, YTD 수익률은 정확한 outcome return ledger가 연결될 때까지 미산출로 둡니다.</div>`;
}"""

    new_view=r"""function usModelPerformanceView(j,marketSnapshot=null){
  const s=j.summary||{},official=n(s.selector_observed_hit_rate_pct);
  const ledger=marketSnapshot?.payload?.source_payload?.r5_shadow_ledger||{};
  const ls=ledger.summary||{};
  const hasLedger=Array.isArray(ledger.trades)&&ledger.trades.length>0;
  if(hasLedger){
    const compound=n(ls.closed_compound_return_pct),closed=n(ls.closed_count),open=n(ls.open_count);
    return `<div class="model-disclosure"><b>R5.1 실제 모델 · Forward SHADOW ledger</b><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('종료 cycle 복리',compound==null?'—':pct(compound,1),`${fmt(closed,0)}개 closed trade`)}${card('Open',fmt(open,0),esc((ls.open_symbols||[]).join(', ')||'—'))}${card('공식 관측 적중률',official==null?'—':`${official.toFixed(1)}%`,`${fmt(s.selector_prospective_outcomes,0)}개 prospective outcome`)}${card('Ledger',fmt(ls.trade_count,0)+' trades',`${time(s.window_start)} ~ ${time(s.window_end)}`)}</div><div class="notice model-note">R5.1의 저장된 <b>shadow_entry_this_signal</b>과 selector 전환으로 구성한 Forward SHADOW lifecycle입니다. B/S는 실제 주문 체결이 아니라 모델의 가상 ENTER/EXIT이며 거래비용은 반영하지 않습니다.</div>`;
  }
  return `<div class="model-disclosure"><b>R5.1 실제 모델 · SHADOW</b><span>${badge('실거래 아님','warn')}</span></div><div class="grid4 model-kpis">${card('R5.1 수익률','미산출','lifecycle ledger 없음')}${card('공식 관측 적중률',official==null?'—':`${official.toFixed(1)}%`,`${fmt(s.selector_prospective_outcomes,0)}개 prospective outcome`)}${card('관측 일수',fmt(s.prospective_distinct_days,0),`${fmt(s.distinct_model_snapshots,0)}개 model snapshot`)}${card('Shadow 신호',fmt(s.shadow_signal_count,0),`${time(s.window_start)} ~ ${time(s.window_end)}`)}</div><div class="notice model-note">Forward SHADOW lifecycle 데이터가 아직 없어서 공식 prospective 통계만 표시합니다.</div>`;
}"""
    app=delta_replace(app,old_view,new_view,"US ledger summary")

    app=delta_replace(
        app,
        "if(m==='US'){const signalChart=await usShadowSignalChart(marketSnapshot);box.innerHTML=usModelPerformanceView(j)+signalChart;}",
        "if(m==='US'){const signalChart=await usShadowSignalChart(marketSnapshot);box.innerHTML=usModelPerformanceView(j,marketSnapshot)+signalChart;}",
        "US loader summary binding",
    )

    app=delta_replace(
        app,
        """const metricLabel=actual?(meta.signalOnly?'모델 신호':'모델 YTD'):'전략 YTD';
  const ruleLabel=meta.signalOnly?'R5.1 SHADOW 모델 신호 · 실제 체결 아님':(actual?String(meta.rule||sm.rule||'실제 모델')+' ledger · 종목별 복리 + 미실현 MTM · 거래비용 별도':'MA20/60 추세 시뮬레이션 · 거래비용 제외');
  const legendLabel=meta.signalOnly?'<b class="buy-text">B 모델 BUY</b> · <b class="sell-text">S 모델 SELL</b>':'<b class="buy-text">B 매수</b> · <b class="sell-text">S 매도</b>';""",
        """const metricLabel=actual?(meta.lifecycle?'SHADOW PnL':(meta.signalOnly?'모델 신호':'모델 YTD')):'전략 YTD';
  const ruleLabel=meta.lifecycle?'R5.1 Forward SHADOW lifecycle · 실제 체결 아님 · 거래비용 제외':(meta.signalOnly?'R5.1 SHADOW 모델 신호 · 실제 체결 아님':(actual?String(meta.rule||sm.rule||'실제 모델')+' ledger · 종목별 복리 + 미실현 MTM · 거래비용 별도':'MA20/60 추세 시뮬레이션 · 거래비용 제외'));
  const legendLabel=(meta.signalOnly||meta.lifecycle)?'<b class="buy-text">B 모델 BUY</b> · <b class="sell-text">S 모델 SELL</b>':'<b class="buy-text">B 매수</b> · <b class="sell-text">S 매도</b>';""",
        "lifecycle chart labels",
    )

    for marker in (
        "R5_1_SHADOW_LEDGER",
        "R5.1 Forward SHADOW lifecycle",
        "shadow_entry_this_signal",
        "STRICT_TOP3_ACTUAL_LEDGER",
    ):
        if marker not in app:
            raise SystemExit(f"[FAIL] v7.4.13 marker missing: {marker}")

    index=index.replace("vNext.7.4.12","vNext.7.4.13")
    health=health.replace("vNext.7.4.12","vNext.7.4.13")
    health=health.replace(
        "R5.1_SHADOW_HITRATE_ONLY_NO_YTD_RETURN_LEDGER",
        "R5.1_SHADOW_LIFECYCLE_LEDGER",
    )
    health=health.replace(
        "BUFFER_3_5_LEDGER_YTD",
        "STRICT_TOP3_LEDGER_YTD",
    )

    api_count=len(list((root/"api").rglob("*.js")))
    if api_count != 12:
        raise SystemExit(f"[FAIL] v7.4.13 function count changed: {api_count}")
    for p in list((root/"api").rglob("*.js")) + list((root/"lib").rglob("*.js")):
        t=p.read_text(encoding="utf-8")
        if "req.query" in t or "url.parse(" in t:
            raise SystemExit(f"[FAIL] query-parser regression token in {p.relative_to(root)}")

    app_path.write_text(app,encoding="utf-8")
    index_path.write_text(index,encoding="utf-8")
    health_path.write_text(health,encoding="utf-8")
    dashboard_path.write_text(dashboard,encoding="utf-8")
    print("[PASS] vNext.7.4.13 US R5.1 lifecycle ledger UI")
    print("[PASS] KR STRICT_TOP3 + account + SHADOW bundle preserved")
    print("[PASS] API function count = 12")
    sys.exit(0)

# vNext.7.4.12: actual-model BUY/SELL visualization on top of the already
# verified vNext.7.4.11 account/SHADOW bundle.
if "vNext.7.4.11" not in index or "accountKrw" not in app:
    raise SystemExit("[FAIL] vNext.7.4.11 base markers missing")

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f"[FAIL] {label}: expected 1 match, got {count}")
    return text.replace(old,new,1)

helper_anchor="function usModelPerformanceView(j){"
model_helpers=r"""
function krActualLedgerEvents(symbol,marketSnapshot){
  const ledger=marketSnapshot?.payload?.source_payload?.ledger?.top3_event_history||[];
  return ledger
    .filter(e=>String(e.Code||e.code||'').toUpperCase()===String(symbol||'').toUpperCase())
    .map(e=>{
      const typ=String(e.event_type||'').toUpperCase();
      const signal=typ.includes('EXIT')?'SELL':(typ.includes('ENTER')?'BUY':null);
      return signal?{time:e.event_date,price:n(e.close),signal,event_type:typ,source:'STRICT_TOP3_ACTUAL_LEDGER'}:null;
    })
    .filter(Boolean)
    .sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
}
function hydrateKrActualItem(item,marketSnapshot){
  const events=krActualLedgerEvents(item?.symbol,marketSnapshot);
  const rows=item?.rows||[];
  const priceAt=(time,fallback)=>{
    const target=Date.parse(time);let best=null,bestD=Infinity;
    for(const r of rows){
      const p=n(r.close),d=Math.abs(Date.parse(r.time)-target);
      if(p!=null&&d<bestD){best=p;bestD=d}
    }
    return n(fallback)??best;
  };
  const normalized=events.map(e=>({...e,price:priceAt(e.time,e.price)})).filter(e=>e.price!=null);
  let open=null,multiple=1,closed=0,wins=0;
  for(const e of normalized){
    if(e.signal==='BUY'){if(!open)open=e;continue}
    if(e.signal==='SELL'&&open&&open.price>0){
      const r=e.price/open.price-1;multiple*=1+r;closed++;if(r>0)wins++;open=null;
    }
  }
  const last=n(rows.at(-1)?.close);
  let openPosition=null;
  if(open&&open.price>0&&last!=null){
    openPosition={entry_time:open.time,entry_price:open.price,current_price:last,return_pct:(last/open.price-1)*100};
    multiple*=last/open.price;
  }
  return {...item,events:normalized,source:'ACTUAL_MODEL_LEDGER',summary:{...(item?.summary||{}),strategy_return_pct:(multiple-1)*100,closed_trades:closed,win_rate_pct:closed?wins/closed*100:null,open_position:openPosition,rule:'STRICT_TOP3'}};
}
async function usShadowSignalChart(marketSnapshot){
  const selector=marketSnapshot?.payload?.source_payload?.today_selector||{};
  const symbol=String(selector.selected_symbol||'').toUpperCase();
  if(!symbol)return '<div class="notice">현재 표시 가능한 R5.1 모델 신호가 없습니다.</div>';
  const hist=await getJSON('/api/history?mode=ytd-points&market=US&assets='+encodeURIComponent(symbol));
  const raw=(hist.items||[]).find(x=>String(x.symbol||'').toUpperCase()===symbol);
  if(!raw)return '<div class="notice">현재 모델 선택 종목의 가격 이력이 없습니다.</div>';
  const events=[];
  if(selector.shadow_entry_this_signal===true){
    events.push({time:selector.as_of_utc,price:n(selector.reference_price),signal:'BUY',event_type:'R5_1_SHADOW_ENTRY',source:'R5.1_SHADOW_SIGNAL'});
  }
  const item={...raw,events,summary:{...(raw.summary||{}),strategy_return_pct:null,closed_trades:0,win_rate_pct:null,open_position:null,rule:'R5.1 SHADOW SIGNAL'}};
  return '<div class="section"><div class="section-title"><h3>현재 R5.1 모델 신호</h3><span class="small">SHADOW · 체결 아님</span></div>'+ytdPointChart(item,{name:symbol,actualModel:true,signalOnly:true,rule:'R5.1 SHADOW'})+'</div>';
}
"""
if helper_anchor not in app:
    raise SystemExit("[FAIL] model-performance UI anchor missing")
app=app.replace(helper_anchor,model_helpers+helper_anchor,1)

app=replace_once(
    app,
    """const metricLabel=actual?'모델 YTD':'전략 YTD';
  const ruleLabel=actual?`${meta.rule||sm.rule||'실제 모델'} ledger · 종목별 복리 + 미실현 MTM · 거래비용 별도`:'MA20/60 추세 시뮬레이션 · 거래비용 제외';""",
    """const metricLabel=actual?(meta.signalOnly?'모델 신호':'모델 YTD'):'전략 YTD';
  const ruleLabel=meta.signalOnly?'R5.1 SHADOW 모델 신호 · 실제 체결 아님':(actual?String(meta.rule||sm.rule||'실제 모델')+' ledger · 종목별 복리 + 미실현 MTM · 거래비용 별도':'MA20/60 추세 시뮬레이션 · 거래비용 제외');
  const legendLabel=meta.signalOnly?'<b class="buy-text">B 모델 BUY</b> · <b class="sell-text">S 모델 SELL</b>':'<b class="buy-text">B 매수</b> · <b class="sell-text">S 매도</b>';""",
    "actual-model labels",
)
app=replace_once(
    app,
    '<span class="trade-legend"><b class="buy-text">B 매수</b> · <b class="sell-text">S 매도</b></span>',
    '<span class="trade-legend">${legendLabel}</span>',
    "actual-model legend",
)
app=replace_once(app,"async function loadActualModelPerformance(m,assets){","async function loadActualModelPerformance(m,assets,marketSnapshot=null){","actual loader signature")
app=replace_once(
    app,
    "if(m==='US')box.innerHTML=usModelPerformanceView(j);",
    "if(m==='US'){const signalChart=await usShadowSignalChart(marketSnapshot);box.innerHTML=usModelPerformanceView(j)+signalChart;}",
    "US model signal chart",
)
# Patch KR hydration only inside loadActualModelPerformance(). The same
# "const by=new Map(...)" expression also exists in loadYtdStockCharts().
loader_start=app.find("async function loadActualModelPerformance(")
loader_end=app.find("\nfunction bindPerformanceTabs(", loader_start)
if loader_start < 0 or loader_end < 0:
    raise SystemExit("[FAIL] loadActualModelPerformance block missing")
loader=app[loader_start:loader_end]
loader_old="const by=new Map((j.items||[]).map(x=>[String(x.symbol).toUpperCase(),x]));"
if loader.count(loader_old) != 1:
    raise SystemExit(
        f"[FAIL] KR actual ledger hydration inside loader: "
        f"expected 1 match, got {loader.count(loader_old)}"
    )
loader=loader.replace(
    loader_old,
    """const hydrated=(j.items||[]).map(x=>hydrateKrActualItem(x,marketSnapshot));
      const by=new Map(hydrated.map(x=>[String(x.symbol).toUpperCase(),x]));""",
    1,
)
app=app[:loader_start]+loader+app[loader_end:]
app=replace_once(app,"function bindPerformanceTabs(m,assets){","function bindPerformanceTabs(m,assets,marketSnapshot=null){","tab binding signature")
app=replace_once(
    app,
    "if(btn.dataset.performanceMode==='model')loadActualModelPerformance(m,assets);",
    "if(btn.dataset.performanceMode==='model')loadActualModelPerformance(m,assets,marketSnapshot);",
    "tab model loader",
)
app=replace_once(
    app,
    "if(m==='US'){const a=(j.payload?.top3||[]).slice(0,3);bindPerformanceTabs('US',a);loadYtdStockCharts('US',a)}",
    "if(m==='US'){const a=(j.payload?.top3||[]).slice(0,3);bindPerformanceTabs('US',a,j);loadYtdStockCharts('US',a)}",
    "US market snapshot binding",
)
app=replace_once(
    app,
    "if(m==='KR'){const a=(j.payload?.assets||j.payload?.top3||[]).slice(0,5);bindPerformanceTabs('KR',a);loadYtdStockCharts('KR',a)}",
    "if(m==='KR'){const a=(j.payload?.assets||j.payload?.top3||[]).slice(0,5);bindPerformanceTabs('KR',a,j);loadYtdStockCharts('KR',a)}",
    "KR market snapshot binding",
)

for marker in ("STRICT_TOP3_ACTUAL_LEDGER","R5_1_SHADOW_ENTRY","hydrateKrActualItem","usShadowSignalChart","B 모델 BUY"):
    if marker not in app:
        raise SystemExit(f"[FAIL] v7.4.12 marker missing: {marker}")
if "\\n      const by=new Map(hydrated" in app:
    raise SystemExit("[FAIL] literal backslash-n leaked into app.js")

index=index.replace("vNext.7.4.11","vNext.7.4.12")
health=health.replace("vNext.7.4.11","vNext.7.4.12")

api_count=len(list((root/"api").rglob("*.js")))
if api_count != 12:
    raise SystemExit(f"[FAIL] function count changed: {api_count}")
for p in list((root/"api").rglob("*.js")) + list((root/"lib").rglob("*.js")):
    t=p.read_text(encoding="utf-8")
    if "req.query" in t or "url.parse(" in t:
        raise SystemExit(f"[FAIL] query-parser regression token in {p.relative_to(root)}")

app_path.write_text(app,encoding="utf-8")
index_path.write_text(index,encoding="utf-8")
health_path.write_text(health,encoding="utf-8")
dashboard_path.write_text(dashboard,encoding="utf-8")
print("[PASS] vNext.7.4.12 KR actual ledger B/S + US model signal UI")
print("[PASS] API function count = 12")
sys.exit(0)

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
    "vNext.7.4.12 · Account + Forward SHADOW Read Only",
    1,
)

# Health metadata only; contracts/model/risk logic are untouched.
health=health.replace("vNext.7.4.9","vNext.7.4.12")

# Verify the read-only account route remains resolvable through the recovered
# 12-function routing graph. The account backend itself is intentionally not
# modified by this UI deployment.
account_target=resolve_api_route("/api/account")
print(f"[INFO] account route target: {account_target.relative_to(root)}")

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
assert "vNext.7.4.12" in index

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
assert x.get("investment_hub_version") == "vNext.7.4.18", x.get("investment_hub_version")
assert x.get("root_ui_version") == "vNext.7.4.18", x.get("root_ui_version")
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
assert isinstance(x.get("trade_execution"), bool)
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

vcurl "/api/dashboard?market=KR" "${WORK}/candidate-kr.json"
vcurl "/api/dashboard?market=US" "${WORK}/candidate-us.json"
python3 - "${WORK}/candidate-kr.json" "${WORK}/candidate-us.json" <<'PY'
import json,sys
kr,us=(json.load(open(p,encoding="utf-8")) for p in sys.argv[1:])
ledger=((((kr.get("payload") or {}).get("source_payload") or {}).get("ledger") or {}).get("top3_event_history") or [])
assert len(ledger)>0, "KR top3_event_history empty"
types={str(x.get("event_type") or "") for x in ledger}
assert any("ENTER" in x for x in types), types
assert any("EXIT" in x for x in types), types
src=((us.get("payload") or {}).get("source_payload") or {})
selector=(src.get("today_selector") or {})
assert selector.get("selected_symbol"), selector
r5=(src.get("r5_shadow_ledger") or {})
trades=r5.get("trades") or []
events=r5.get("events") or []
assert len(trades)>=1, r5
assert any(str(x.get("signal") or "")=="BUY" for x in events), events
assert any(str(x.get("signal") or "")=="SELL" for x in events), events
assert r5.get("shadow_only") is True
assert r5.get("execution") is False
annual=r5.get("annual_2026") or {}
if annual:
    assert annual.get("official_ytd") is False
    assert (annual.get("reconstructed") or {}).get("in_sample_warning") is True
    assert (annual.get("forward") or {}).get("prospective") is True
    assert len(annual.get("trades") or []) >= len(trades)
    print(f"[PASS] candidate US 2026 annual ledger trades={len(annual.get('trades') or [])}")
else:
    print("[INFO] annual_2026 not published yet; Forward fallback remains valid")
print(f"[PASS] candidate KR actual ledger events={len(ledger)}")
print(f"[PASS] candidate US R5.1 lifecycle trades={len(trades)} events={len(events)}")
PY

vercel curl "${CANDIDATE}/app.js" -- --silent --show-error >"${WORK}/candidate-app.js"
grep -q "accountKrw" "${WORK}/candidate-app.js" || fail "candidate app.js lacks KRW mapping"
grep -q "fmt(qty(h),6)" "${WORK}/candidate-app.js" || fail "candidate app.js lacks fractional quantity precision"
grep -q "renderShadow" "${WORK}/candidate-app.js" || fail "candidate app.js lacks SHADOW read-only renderer"
grep -q "STRICT_TOP3_ACTUAL_LEDGER" "${WORK}/candidate-app.js" || fail "candidate app.js lacks KR actual ledger B/S"
grep -q "R5_1_ANNUAL_2026_LEDGER" "${WORK}/candidate-app.js" || fail "candidate app.js lacks US 2026 annual ledger renderer"
grep -q "R5.1 2026 Annual Ledger" "${WORK}/candidate-app.js" || fail "candidate app.js lacks US 2026 annual ledger UI"
grep -q "2026 전체 Ledger" "${WORK}/candidate-app.js" || fail "candidate app.js lacks full annual ledger browser"
grep -q "annual-ledger-scroll" "${WORK}/candidate-app.js" || fail "candidate app.js lacks annual ledger scroll region"
grep -q "hydrateKrActualItem" "${WORK}/candidate-app.js" || fail "candidate app.js lacks KR actual ledger hydration"
grep -q "renderCommandAccount" "${WORK}/candidate-app.js" || fail "candidate app.js lacks command center account"
grep -q "R5.1 Top 6" "${WORK}/candidate-app.js" || fail "candidate app.js lacks US Top-6 workspace"
grep -q "usLedgerTable" "${WORK}/candidate-app.js" || fail "candidate app.js lacks structured ledger table"
grep -q "usModelTable" "${WORK}/candidate-app.js" || fail "candidate app.js lacks model universe table"
grep -q "loadUsPrimaryChart" "${WORK}/candidate-app.js" || fail "candidate app.js lacks dedicated US primary chart"
grep -q "commandNextActions" "${WORK}/candidate-app.js" || fail "candidate app.js lacks NEXT ACTIONS"
grep -q "WAITING FOR FRESH US SNAPSHOT" "${WORK}/candidate-app.js" || fail "candidate app.js lacks execution freshness guard"
grep -q "SELL PREVIEW" "${WORK}/candidate-app.js" || fail "candidate app.js lacks stale action preview"
grep -q "EXECUTION_FRESH_MINUTES=90" "${WORK}/candidate-app.js" || fail "candidate app.js lacks 90m execution freshness"
vercel curl "${CANDIDATE}/" -- --silent --show-error >"${WORK}/candidate-index.html"
grep -q "Investment Intelligence" "${WORK}/candidate-index.html" || fail "candidate index lacks command-center header"
grep -q "commandHealth" "${WORK}/candidate-index.html" || fail "candidate index lacks system-health panel"
grep -q "UNIVERSE_BASELINE_TOTAL=102" "${WORK}/candidate-app.js" || fail "candidate Universe baseline marker missing"
grep -q "function loadUniverse()" "${WORK}/candidate-app.js" || fail "candidate Universe loader missing"
grep -q "US R5.1 UNIVERSE" "${WORK}/candidate-app.js" || fail "candidate Universe renderer missing"
grep -q "universeTab" "${WORK}/candidate-index.html" || fail "candidate Universe nav missing"
grep -q "Command Center + Universe View" "${WORK}/candidate-index.html" || fail "candidate Universe footer marker missing"
echo "[PASS] candidate UI bundle + inline Universe view + model B/S markers"

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
    x.get("investment_hub_version")=="vNext.7.4.18"
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
echo "[PASS] production vNext.7.4.18 health"

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
  if grep -q "accountKrw" "${WORK}/prod-app.js"      && grep -q "fmt(qty(h),6)" "${WORK}/prod-app.js"      && grep -q "renderShadow" "${WORK}/prod-app.js" \
     && grep -q "STRICT_TOP3_ACTUAL_LEDGER" "${WORK}/prod-app.js" \
     && grep -q "R5_1_ANNUAL_2026_LEDGER" "${WORK}/prod-app.js" \
     && grep -q "R5.1 2026 Annual Ledger" "${WORK}/prod-app.js" \
     && grep -q "2026 전체 Ledger" "${WORK}/prod-app.js" \
     && grep -q "annual-ledger-scroll" "${WORK}/prod-app.js" \
     && grep -q "renderCommandAccount" "${WORK}/prod-app.js" \
     && grep -q "R5.1 Top 6" "${WORK}/prod-app.js" \
     && grep -q "usLedgerTable" "${WORK}/prod-app.js" \
     && grep -q "usModelTable" "${WORK}/prod-app.js" \
     && grep -q "loadUsPrimaryChart" "${WORK}/prod-app.js" \
     && grep -q "commandNextActions" "${WORK}/prod-app.js" \
     && grep -q "WAITING FOR FRESH US SNAPSHOT" "${WORK}/prod-app.js" \
     && grep -q "EXECUTION_FRESH_MINUTES=90" "${WORK}/prod-app.js"; then
    APP_READY=true
    break
  fi
  sleep 2
done

if [ "${APP_READY}" != true ]; then
  rollback
  fail "production UI marker missing"
fi

grep -q "UNIVERSE_BASELINE_TOTAL=102" "${WORK}/prod-app.js" || { rollback; fail "production Universe baseline marker missing"; }
grep -q "function loadUniverse()" "${WORK}/prod-app.js" || { rollback; fail "production Universe loader missing"; }
curl -fsS --max-time 20 "${PROD_URL}/" >"${WORK}/prod-index.html"
grep -q "universeTab" "${WORK}/prod-index.html" || { rollback; fail "production Universe nav missing"; }

echo "[PASS] production account + dashboard + SHADOW read-only + UI + inline Universe"

echo
echo "[8/8] Gateway live-trading gate verification"
curl -fsS --max-time 5 http://127.0.0.1:8787/health >"${WORK}/gateway-health.json"
python3 - "${WORK}/gateway-health.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1], encoding="utf-8"))
assert x.get("status")=="ok"
assert isinstance(x.get("tradingEnabled"), bool)
assert isinstance(x.get("liveGateOpen"), bool)
print("[PASS] gateway health readable")
print("[INFO] tradingEnabled=", x.get("tradingEnabled"))
print("[INFO] liveGateOpen=", x.get("liveGateOpen"))
print("[INFO] manualTradingEnabled=", x.get("manualTradingEnabled"))
print("[INFO] manualLiveGateOpen=", x.get("manualLiveGateOpen"))
PY

echo
echo "=================================================="
echo "PRODUCTION COMPLETE"
echo "=================================================="
echo "URL: ${PROD_URL}"
echo "Version: vNext.7.4.18"
echo "Account: Toss USD originals + KRW reference conversion"
echo "Universe: /?view=universe · full R5.1 ranking table"
echo "KR actual model: STRICT_TOP3 ledger B/S"
echo "US actual model: R5.1 2026 RECON + canonical Forward SHADOW ledger"
echo "FX: browser-side OPEN-ER -> Frankfurter fallback"
echo "API functions: 12"
echo "SHADOW web: READ ONLY"
echo "Automated trade execution: gateway-controlled (state preserved by web deploy)"
echo "Manual trade gate: managed separately by configure_manual_live_trading_env.sh"
echo "Recovered source backup:"
echo "  /root/kalman-hub-v749-source-${STAMP}.tar.gz"
echo "Work log:"
echo "  ${WORK}"
echo "=================================================="
