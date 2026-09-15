#!/usr/bin/env bash
set -euo pipefail

SRC_ROOT="${KALMAN_SOURCE_ROOT:-/opt/kalman/src/Codex/kalman-toss-gateway}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
GATEWAY_SERVICE="${KALMAN_GATEWAY_SERVICE:-kalman-toss-gateway.service}"
SHADOW_TIMER="${KALMAN_SHADOW_TIMER:-kalman-shadow-bakeoff-daily.timer}"
HUB_URL="${KALMAN_HUB_URL:-https://kalman-investment-hub-v2.vercel.app}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

for f in   "$SRC_ROOT/app/main.py"   "$SRC_ROOT/app/config.py"   "$SRC_ROOT/app/risk.py"   "$SRC_ROOT/app/executor.py"   "$SRC_ROOT/scripts/deploy_investment_hub_shadow_proxy.sh"   "$SRC_ROOT/scripts/configure_manual_live_trading_env.sh"   "$SRC_ROOT/scripts/run_shadow_bakeoff_daily.sh"   "$SRC_ROOT/scripts/run_shadow_bakeoff_v1.sh"
do
  [ -f "$f" ] || {
    echo "[FAIL] missing source file: $f" >&2
    exit 2
  }
done

[ -x "$PY" ] || {
  echo "[FAIL] production Python missing: $PY" >&2
  exit 3
}

[ -f "$ENV_FILE" ] || {
  echo "[FAIL] env file missing: $ENV_FILE" >&2
  exit 4
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/opt/kalman/state/deploy-backups/manual-shadow-${STAMP}"
mkdir -p "$BACKUP"

TIMER_WAS_ENABLED=false
if systemctl is-enabled "$SHADOW_TIMER" >/dev/null 2>&1; then
  TIMER_WAS_ENABLED=true
  systemctl disable --now "$SHADOW_TIMER" >/dev/null 2>&1 || true
fi

MANUAL_GATE_OPENED=false

cleanup() {
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$MANUAL_GATE_OPENED" = "true" ]; then
    echo "[ROLLBACK] closing manual live gate after failed deployment" >&2
    "$APP_ROOT/scripts/configure_manual_live_trading_env.sh" disable >/dev/null 2>&1 || true
  fi
  if [ "$TIMER_WAS_ENABLED" = "true" ]; then
    systemctl enable --now "$SHADOW_TIMER" >/dev/null 2>&1 || true
  fi
  return "$rc"
}
trap cleanup EXIT

echo "============================================================"
echo "KALMAN — SHADOW READ-ONLY WEB + MANUAL LIVE BROKER"
echo "============================================================"

echo
echo "[1/8] Back up current runtime"
cp -a "$APP_ROOT/app" "$BACKUP/app" 2>/dev/null || true
mkdir -p "$BACKUP/scripts"
for name in   run_shadow_bakeoff_daily.sh   run_shadow_bakeoff_v1.sh   install_market_research_v2.sh   install_shadow_bakeoff_systemd.sh   deploy_investment_hub_shadow_proxy.sh   configure_manual_live_trading_env.sh   trading_status.sh
do
  [ -f "$APP_ROOT/scripts/$name" ] && cp -a "$APP_ROOT/scripts/$name" "$BACKUP/scripts/$name" || true
done
echo "backup=$BACKUP"

echo
echo "[2/8] Deploy gateway + hardened SHADOW scripts"
mkdir -p "$APP_ROOT/app" "$APP_ROOT/scripts"
cp -a "$SRC_ROOT/app/." "$APP_ROOT/app/"
for name in   run_shadow_bakeoff_daily.sh   run_shadow_bakeoff_v1.sh   install_market_research_v2.sh   install_shadow_bakeoff_systemd.sh   deploy_investment_hub_shadow_proxy.sh   configure_manual_live_trading_env.sh   trading_status.sh
do
  install -m 0755 "$SRC_ROOT/scripts/$name" "$APP_ROOT/scripts/$name"
done

PYTHONPATH="$APP_ROOT" "$PY" -m compileall -q "$APP_ROOT/app"
for f in   "$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"   "$APP_ROOT/scripts/run_shadow_bakeoff_v1.sh"   "$APP_ROOT/scripts/deploy_investment_hub_shadow_proxy.sh"   "$APP_ROOT/scripts/configure_manual_live_trading_env.sh"
do
  bash -n "$f"
done
echo "RUNTIME_DEPLOY_GATE=PASS"

echo
echo "[3/8] Restart gateway and verify SHADOW read-only endpoint"
systemctl restart "$GATEWAY_SERVICE"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8787/health >/tmp/kalman-gateway-health.json 2>/dev/null; then
    break
  fi
  sleep 1
done

PYTHONPATH="$APP_ROOT" "$PY" - "$ENV_FILE" <<'PY'
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

env = dotenv_values(sys.argv[1])
secret = str(env.get("HUB_GATEWAY_SECRET") or "")
if not secret:
    raise SystemExit("[FAIL] HUB_GATEWAY_SECRET missing")

health = httpx.get("http://127.0.0.1:8787/health", timeout=5).json()
assert health.get("status") == "ok"
assert health.get("tradingEnabled") is False
assert health.get("liveGateOpen") is False

r = httpx.get(
    "http://127.0.0.1:8787/api/shadow-bakeoff",
    headers={"X-Gateway-Secret": secret},
    timeout=10,
)
r.raise_for_status()
x = r.json()
assert x.get("status") == "READY"
assert x.get("schema_version") == "kalman-shadow-readonly-v1"
inv = x.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
assert all(k in (x.get("signals") or {}) for k in ("US", "KR", "BTC"))
print("GATEWAY_SHADOW_READONLY_GATE=PASS")
PY

echo
echo "[4/8] Deploy verified SHADOW read-only Investment Hub"
KALMAN_HUB_PROD_URL="$HUB_URL"   bash "$APP_ROOT/scripts/deploy_investment_hub_shadow_proxy.sh"

echo
echo "[5/8] Verify production web SHADOW endpoint"
"$PY" - "$HUB_URL" <<'PY'
import sys
import httpx

base = sys.argv[1].rstrip("/")
health = httpx.get(base + "/api/health", timeout=20)
health.raise_for_status()
h = health.json()
assert h.get("investment_hub_version") == "vNext.7.4.11"

shadow = httpx.get(base + "/api/dashboard?market=SHADOW", timeout=20)
shadow.raise_for_status()
x = shadow.json()
assert x.get("status") == "READY"
assert x.get("schema_version") == "kalman-shadow-readonly-v1"
inv = x.get("invariants") or {}
assert inv.get("read_only") is True
assert inv.get("trade_execution") is False
print("WEB_SHADOW_READONLY_GATE=PASS")
PY

echo
echo "[6/8] Arm MANUAL live trading only"
"$APP_ROOT/scripts/configure_manual_live_trading_env.sh" enable
MANUAL_GATE_OPENED=true

echo
echo "[7/8] Real broker connection + manual preview smoke"
PYTHONPATH="$APP_ROOT" "$PY" - "$ENV_FILE" <<'PY'
from datetime import datetime, timezone
import sys

import httpx
from dotenv import dotenv_values

env = dotenv_values(sys.argv[1])
secret = str(env.get("HUB_GATEWAY_SECRET") or "")
if not secret:
    raise SystemExit("[FAIL] HUB_GATEWAY_SECRET missing")

headers = {
    "X-Gateway-Secret": secret,
    "Content-Type": "application/json",
}

health = httpx.get("http://127.0.0.1:8787/health", timeout=5).json()
assert health.get("tradingEnabled") is False
assert health.get("liveGateOpen") is False
assert health.get("manualTradingEnabled") is True
assert health.get("manualLiveGateOpen") is True

accounts = httpx.get(
    "http://127.0.0.1:8787/api/accounts",
    headers={"X-Gateway-Secret": secret},
    timeout=15,
)
accounts.raise_for_status()

holdings = httpx.get(
    "http://127.0.0.1:8787/api/holdings",
    headers={"X-Gateway-Secret": secret},
    timeout=15,
)
holdings.raise_for_status()

orders = httpx.get(
    "http://127.0.0.1:8787/api/orders?status=OPEN",
    headers={"X-Gateway-Secret": secret},
    timeout=15,
)
orders.raise_for_status()

client_id = "preview-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
preview = httpx.post(
    "http://127.0.0.1:8787/api/order-preview",
    headers=headers,
    json={
        "client_order_id": client_id,
        "symbol": "SPY",
        "side": "BUY",
        "order_type": "MARKET",
        "time_in_force": "DAY",
        "order_amount": "1",
    },
    timeout=20,
)
preview.raise_for_status()
p = preview.json()
assert p.get("executionAttempted") is False
assert p.get("allowed") is True, p

print("REAL_BROKER_READ_GATE=PASS")
print("MANUAL_ORDER_PREVIEW_GATE=PASS")
print("executionAttempted=false")
print("manualLiveGateOpen=true")
print("autoLiveGateOpen=false")
PY

echo
echo "[8/8] Restore/verify SHADOW timer"
if [ "$TIMER_WAS_ENABLED" = "true" ]; then
  systemctl enable --now "$SHADOW_TIMER" >/dev/null
fi

echo "timer_enabled=$(systemctl is-enabled "$SHADOW_TIMER" 2>/dev/null || true)"
echo "timer_active=$(systemctl is-active "$SHADOW_TIMER" 2>/dev/null || true)"

echo
echo "=== FINAL TRADING STATUS ==="
"$APP_ROOT/scripts/trading_status.sh"

echo
echo "============================================================"
echo "KALMAN_SHADOW_READONLY_MANUAL_LIVE_COMPLETE"
echo "Automatic trading: DISABLED / DRY_RUN"
echo "Manual live trading: ARMED"
echo "No order was submitted by this deployment."
echo "WEB_DASHBOARD=$HUB_URL"
echo "============================================================"
