#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
GUARDED="$APP_ROOT/scripts/run_unified_guarded.sh"
PROD_URL="${KALMAN_HUB_PROD_URL:-https://kalman-investment-hub-v2.vercel.app}"
LOG_DIR="${KALMAN_LOG_DIR:-/opt/kalman/logs}"
STATE_DIR="${KALMAN_STATE_DIR:-/opt/kalman/state}"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
mkdir -p "$LOG_DIR" "$STATE_DIR"

[ "$(id -u)" -eq 0 ] || fail "run as root: sudo /bin/bash $0"
[ -d "$APP_ROOT" ] || fail "app root missing: $APP_ROOT"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -x "$PY" ] || fail "python missing: $PY"
[ -f "$GUARDED" ] || fail "guarded unified runner missing: $GUARDED"

export KALMAN_APP_ROOT="$APP_ROOT"
export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "============================================================"
echo "Kalman Investment Hub — DB sync + account repair"
echo "============================================================"
echo "Production: $PROD_URL"
echo

echo "[1/8] Safety gates"
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v=dotenv_values(Path(sys.argv[1]))
trading=str(v.get("TRADING_ENABLED") or "").strip().lower()
live=str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
auto=str(v.get("AUTO_TRADE_ENABLED") or "").strip().lower()
db=bool(str(v.get("DATABASE_URL_WRITER") or "").strip())
secret=bool(str(v.get("HUB_GATEWAY_SECRET") or "").strip())
print("TRADING_ENABLED      =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM =", "SET" if live else "(empty)")
print("AUTO_TRADE_ENABLED   =", auto or "(empty)")
print("DATABASE_URL_WRITER  =", "SET" if db else "MISSING")
print("HUB_GATEWAY_SECRET   =", "SET" if secret else "MISSING")
if trading=="true": raise SystemExit("[FAIL] TRADING_ENABLED=true")
if live: raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set")
if auto=="true": raise SystemExit("[FAIL] AUTO_TRADE_ENABLED=true")
if not db: raise SystemExit("[FAIL] DATABASE_URL_WRITER missing")
if not secret: raise SystemExit("[FAIL] HUB_GATEWAY_SECRET missing")
print("SAFETY=PASS")
PY

echo
echo "[2/8] Google Drive + gateway service"
if [[ "$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v=dotenv_values(Path(sys.argv[1]))
print(v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data")
PY
)" == /mnt/gdrive* ]]; then
  if ! mountpoint -q /mnt/gdrive; then
    systemctl start kalman-gdrive.service || true
    sleep 3
  fi
  mountpoint -q /mnt/gdrive || fail "/mnt/gdrive not mounted"
  timeout 20 ls /mnt/gdrive >/dev/null || fail "/mnt/gdrive unreadable"
fi

systemctl enable kalman-toss-gateway.service >/dev/null 2>&1 || true
systemctl restart kalman-toss-gateway.service
for _ in $(seq 1 20); do
  if curl -fsS --max-time 3 http://127.0.0.1:8787/health >"$STATE_DIR/gateway-health.json" 2>/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:8787/health >"$STATE_DIR/gateway-health.json"   || fail "local gateway health failed"
cat "$STATE_DIR/gateway-health.json"
echo
ss -ltnp | grep ':8787' || fail "gateway is not listening on 8787"

echo
echo "[3/8] Local Toss read-only account check"
"$PY" - "$ENV_FILE" <<'PY'
import asyncio, sys
from pathlib import Path
from dotenv import dotenv_values
import httpx

env=dotenv_values(Path(sys.argv[1]))
secret=str(env.get("HUB_GATEWAY_SECRET") or "")
headers={"x-gateway-secret":secret}

async def main():
    async with httpx.AsyncClient(timeout=20.0) as c:
        probes=[
            "/api/accounts",
            "/api/holdings",
            "/api/buying-power?currency=USD",
            "/api/buying-power?currency=KRW",
        ]
        for p in probes:
            r=await c.get("http://127.0.0.1:8787"+p,headers=headers)
            print(p, "HTTP", r.status_code)
            if r.status_code!=200:
                print(r.text[:1000])
                raise SystemExit("[FAIL] local Toss read-only probe failed")
    print("LOCAL_ACCOUNT_GATEWAY=READY")

asyncio.run(main())
PY

echo
echo "[4/8] Current DB-backed web state"
for m in GLOBAL CRYPTO US KR; do
  code="$(curl -sS -o "$STATE_DIR/web-${m}.json" -w '%{http_code}'     --max-time 20 "$PROD_URL/api/dashboard?market=$m" || true)"
  echo "$m HTTP $code"
  [ "$code" = "200" ] || cat "$STATE_DIR/web-${m}.json" || true
done

echo
echo "[5/8] Refresh Unified DB snapshots under cgroup limits"
# CRYPTO first, then US, then KR_GLOBAL so GLOBAL is rebuilt last from all three.
for mode in CRYPTO_GLOBAL US KR_GLOBAL; do
  echo
  echo "---- $mode ----"
  /bin/bash "$GUARDED" "$mode" | tee "$LOG_DIR/repair-${mode,,}.log"
done

echo
echo "[6/8] Verify Vercel sees newly generated DB snapshots"
"$PY" - "$PROD_URL" <<'PY'
from datetime import datetime, timezone
import json, sys, urllib.request

base=sys.argv[1].rstrip("/")
now=datetime.now(timezone.utc)
bad=[]

for market in ("CRYPTO","US","KR","GLOBAL"):
    with urllib.request.urlopen(f"{base}/api/dashboard?market={market}", timeout=20) as r:
        x=json.loads(r.read().decode())
    generated=x.get("generated_at")
    data=x.get("data_as_of")
    run=x.get("run_id")
    stale=x.get("effective_stale")
    print(f"{market:<6} run={run} generated_at={generated} data_as_of={data} stale={stale}")
    if market in {"CRYPTO","US","KR","GLOBAL"}:
        try:
            dt=datetime.fromisoformat(str(generated).replace("Z","+00:00"))
            age=(now-dt.astimezone(timezone.utc)).total_seconds()
            if age>6*3600:
                bad.append((market,f"generated_at age={age:.0f}s"))
        except Exception as e:
            bad.append((market,f"generated_at parse: {e}"))

if bad:
    raise SystemExit("[FAIL] web snapshots not refreshed: "+repr(bad))
print("WEB_DB_SYNC=PASS")
PY

echo
echo "[7/8] Restore production cron"
install -m 0644 "$APP_ROOT/config/kalman.cron.d" /etc/cron.d/kalman
if systemctl list-unit-files cron.service >/dev/null 2>&1; then
  systemctl reload cron.service || systemctl restart cron.service
elif systemctl list-unit-files crond.service >/dev/null 2>&1; then
  systemctl reload crond.service || systemctl restart crond.service
fi
echo "[PASS] /etc/cron.d/kalman installed"
cat /etc/cron.d/kalman

echo
echo "[8/8] Verify Vercel account route"
ACCOUNT_CODE="$(curl -sS -o "$STATE_DIR/vercel-account.json" -w '%{http_code}'   --max-time 30 "$PROD_URL/api/account" || true)"
echo "Vercel /api/account HTTP $ACCOUNT_CODE"
if [ "$ACCOUNT_CODE" = "200" ]; then
  "$PY" - "$STATE_DIR/vercel-account.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
parts=x.get("parts") or {}
print("status          =",x.get("status"))
print("trade_execution =",x.get("trade_execution"))
print("parts           =",{k:(v or {}).get("ok") for k,v in parts.items()})
if x.get("trade_execution") is not False:
    raise SystemExit("[FAIL] unexpected trade_execution state")
print("VERCEL_ACCOUNT=READY")
PY
else
  echo "[WARN] Local Toss gateway is READY but Vercel still cannot reach it."
  cat "$STATE_DIR/vercel-account.json" || true
  echo
  echo "Sanitized Vercel gateway configuration:"
  if command -v vercel >/dev/null 2>&1; then
    TMP="$(mktemp -d /tmp/kalman-vercel-env.XXXXXX)"
    trap 'rm -rf "$TMP"' EXIT
    mkdir -p "$TMP/.vercel"
    cat >"$TMP/.vercel/project.json" <<'EOF'
{"projectId":"prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1","orgId":"team_eklxTMfdySLBHexmheTiWGCE"}
EOF
    (
      cd "$TMP"
      vercel env pull .env.production --environment=production --yes         --scope insk1285-9320s-projects >/dev/null 2>&1 || true
    )
    "$PY" - "$TMP/.env.production" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values
import sys
p=Path(sys.argv[1])
if not p.exists():
    print("Vercel env pull unavailable")
    raise SystemExit(0)
v=dotenv_values(p)
u=str(v.get("TOSS_GATEWAY_URL") or "")
s=bool(str(v.get("HUB_GATEWAY_SECRET") or ""))
if u:
    x=urlparse(u)
    print("TOSS_GATEWAY_URL =",f"{x.scheme}://{x.hostname or ''}"+(f":{x.port}" if x.port else ""))
else:
    print("TOSS_GATEWAY_URL = MISSING")
print("HUB_GATEWAY_SECRET =", "SET" if s else "MISSING")
PY
    rm -rf "$TMP"
    trap - EXIT
  fi
  echo
  echo "ACCOUNT_PUBLIC_PATH=NEEDS_REPAIR"
  echo "Do NOT enable live trading. Gateway read-only local path is healthy."
  exit 20
fi

echo
echo "============================================================"
echo "REPAIR COMPLETE"
echo "============================================================"
echo "Unified DB -> Vercel dashboard : READY"
echo "Toss local gateway             : READY"
echo "Vercel account                 : READY"
echo "Main cron                      : INSTALLED"
echo "Trade execution                : OFF"
