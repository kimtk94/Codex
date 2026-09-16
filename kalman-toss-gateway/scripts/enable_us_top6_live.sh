#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/enable_us_top6_live.sh" >&2
  exit 1
fi

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="${ENV_FILE}.pre-us-top6-live-${STAMP}"

[ -f "$ENV_FILE" ] || { echo "[FAIL] missing $ENV_FILE" >&2; exit 2; }
[ -x "$PY" ] || { echo "[FAIL] missing python: $PY" >&2; exit 2; }
[ -f "$APP_ROOT/engine/us_top6_rebalancer.py" ] || { echo "[FAIL] US Top-6 executor missing" >&2; exit 2; }

cp -a "$ENV_FILE" "$BACKUP"
chmod 0600 "$BACKUP"

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from dotenv import dotenv_values

path=Path(sys.argv[1])
cfg=dotenv_values(path)
required=("DATABASE_URL_WRITER","TOSS_CLIENT_ID","TOSS_CLIENT_SECRET","TOSS_ACCOUNT","HUB_GATEWAY_SECRET")
missing=[k for k in required if not str(cfg.get(k) or "").strip()]
if missing:
    raise SystemExit("[FAIL] missing required env: "+", ".join(missing))

updates={
    "US_TOP6_PLAN_ENABLED":"true",
    "US_TOP6_PLAN_OUTPUT":"/opt/kalman/state/us_top6_rebalance_plan.json",
    "US_TOP6_AUDIT_LOG":"/opt/kalman/logs/us-top6-orders.jsonl",
    "AUTO_TRADE_MARKET":"US",
    "AUTO_TRADE_PORTFOLIO_MODE":"R5_1_TOP6",
    "AUTO_TRADE_MAX_POSITIONS":"6",
    "AUTO_TRADE_TARGET_PER_SYMBOL_KRW":"5000",
    "AUTO_TRADE_PORTFOLIO_LIMIT_KRW":"30000",
    "AUTO_TRADE_MIN_ORDER_KRW":"1000",
    "AUTO_TRADE_MIN_ORDER_USD":"1",
    "AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES":"90",
    "MAX_SINGLE_ORDER_KRW":"5000",
    "LIVE_MICRO_TOTAL_LIMIT_KRW":"30000",
    "AUTO_TRADE_ENABLED":"true",
    "AUTO_TRADE_EXECUTION_MODE":"LIVE",
    "AUTO_TRADE_US_TOP6_CONFIRM":"CONFIRM_US_TOP6_30000",
    "TRADING_ENABLED":"true",
    "LIVE_TRADING_CONFIRM":"CONFIRM_LIVE_TRADING",
}

lines=path.read_text(encoding="utf-8").splitlines()
out=[]
seen=set()
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        out.append(line)
        continue
    key=line.split("=",1)[0].strip()
    if key in updates:
        if key not in seen:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
    else:
        out.append(line)
if out and out[-1]!="":
    out.append("")
out.append("# --- US R5.1 Top-6 LIVE micro profile ---")
for key,val in updates.items():
    if key not in seen:
        out.append(f"{key}={val}")
tmp=path.with_suffix(path.suffix+".tmp")
tmp.write_text("\n".join(out).rstrip()+"\n",encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
path.chmod(0o600)
PY

echo "[PASS] environment armed; backup=$BACKUP"

systemctl restart kalman-toss-gateway.service

for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8787/health >/tmp/kalman-us-top6-health.json 2>/dev/null; then
    if "$PY" - /tmp/kalman-us-top6-health.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
ok=(
    x.get("status")=="ok"
    and x.get("tradingEnabled") is True
    and x.get("liveGateOpen") is True
    and int((x.get("limits") or {}).get("dailyTotalKrw") or 0)==30000
    and int((x.get("limits") or {}).get("singleOrderKrw") or 0)==5000
)
raise SystemExit(0 if ok else 1)
PY
    then
      break
    fi
  fi
  sleep 1
done

"$PY" - /tmp/kalman-us-top6-health.json <<'PY'
import json,sys
x=json.load(open(sys.argv[1],encoding="utf-8"))
assert x.get("status")=="ok",x
assert x.get("tradingEnabled") is True,x
assert x.get("liveGateOpen") is True,x
assert int(x["limits"]["dailyTotalKrw"])==30000,x
assert int(x["limits"]["singleOrderKrw"])==5000,x
print("[PASS] gateway live gate OPEN")
print("[PASS] limits: 5,000 KRW/order · 30,000 KRW/day")
PY

if [ -f /etc/cron.d/kalman ]; then
  grep -q "run_auto_trade.sh" /etc/cron.d/kalman     || { echo "[FAIL] /etc/cron.d/kalman has no auto-trade worker" >&2; exit 3; }
  echo "[PASS] US trade cron installed"
else
  echo "[FAIL] /etc/cron.d/kalman missing" >&2
  exit 3
fi

echo
echo "=== LIVE WORKER INITIAL RUN ==="
cd "$APP_ROOT"
KALMAN_ENV_FILE="$ENV_FILE" PYTHONPATH="$APP_ROOT" "$PY" -m engine.us_top6_rebalancer

echo
echo "=== STATUS ==="
echo "US-only R5.1 Top-6 LIVE profile is armed."
echo "Max positions: 6"
echo "Target / symbol: 5,000 KRW"
echo "Total buy cap: 30,000 KRW"
echo "Freshness: 90 minutes"
echo "SELL-first: enabled"
echo "Kill switch:"
echo "  sudo $APP_ROOT/scripts/disable_us_top6_live.sh"
