#!/usr/bin/env bash

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash scripts/apply_live_conditional_20000.sh" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
LIVE_APP="/opt/kalman/app"

OWNER="${SUDO_USER:-}"
if [ -z "$OWNER" ] || [ "$OWNER" = "root" ]; then
  OWNER="taehoon"
fi
OWNER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"
PANEL="${R5_CONDITIONAL_PANEL:-$OWNER_HOME/.cache/kalman-r5-topk/output/r5_1_topk_portfolio_v1/r5_topk_common_trade_panel.parquet}"

if [ ! -f "$PANEL" ]; then
  echo "[FAIL] conditional seed panel missing: $PANEL" >&2
  exit 10
fi

echo "===== PRECHECK ====="
python3 -m py_compile   "$SRC/engine/r5_conditional_policy.py"   "$SRC/engine/r5_conditional_live.py"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] py_compile rc=$RC" >&2
  exit "$RC"
fi

echo "===== DERIVE FROZEN LIVE THRESHOLDS ====="
THRESHOLDS="$(sudo -u "$OWNER" /usr/bin/python3 - "$PANEL" <<'PY'
import sys
import pandas as pd

p = sys.argv[1]
z = pd.read_parquet(p).sort_values(["entry_timestamp", "expected_seq"]).copy()
for c in ("rank1_score", "rank2_score"):
    z[c] = pd.to_numeric(z[c], errors="coerce")
rel = (z["rank1_score"] - z["rank2_score"]) / z["rank1_score"].abs().clip(lower=1e-12)
gap = float(rel.dropna().quantile(0.35))
conf = float(z["rank1_score"].dropna().quantile(0.30))
print(f"{gap:.17g} {conf:.17g}")
PY
)"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] threshold derivation rc=$RC" >&2
  exit "$RC"
fi

GAP_THRESHOLD="$(printf '%s' "$THRESHOLDS" | awk '{print $1}')"
CONF_THRESHOLD="$(printf '%s' "$THRESHOLDS" | awk '{print $2}')"

if [ -z "$GAP_THRESHOLD" ] || [ -z "$CONF_THRESHOLD" ]; then
  echo "[FAIL] thresholds empty" >&2
  exit 11
fi

echo "gap_threshold=$GAP_THRESHOLD"
echo "confidence_threshold=$CONF_THRESHOLD"

echo
echo "===== POLICY TEST ====="
sudo -u "$OWNER" bash -lc "cd '$SRC' && python3 -m pytest tests/test_r5_conditional_policy.py -q"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] policy tests rc=$RC" >&2
  exit "$RC"
fi

echo
echo "===== DEPLOY RUNTIME ====="
KALMAN_ENV_FILE="$ENV_FILE" bash "$SRC/scripts/apply_live_canary_5000.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] base runtime deployment rc=$RC" >&2
  exit "$RC"
fi

echo
echo "===== ENABLE CONDITIONAL LIVE 20K ====="
AUTO_TRADE_CONDITIONAL_GAP_THRESHOLD="$GAP_THRESHOLD" AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD="$CONF_THRESHOLD" KALMAN_ENV_FILE="$ENV_FILE" bash "$LIVE_APP/scripts/configure_auto_trade_env.sh" live-conditional-20000
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] conditional env config rc=$RC" >&2
  exit "$RC"
fi

systemctl restart kalman-toss-gateway.service
sleep 2
systemctl is-active --quiet kalman-toss-gateway.service
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] gateway service not active" >&2
  exit "$RC"
fi

echo
echo "===== LIVE CONFIG ====="
grep -E '^(AUTO_TRADE_ENABLED|AUTO_TRADE_EXECUTION_MODE|AUTO_TRADE_SIGNAL_POLICY|AUTO_TRADE_STRATEGY_VERSION|AUTO_TRADE_ORDER_KRW|AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL|AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW|AUTO_TRADE_CONDITIONAL_|MAX_SINGLE_ORDER_KRW|TRADING_ENABLED|LIVE_TRADING_CONFIRM)=' "$ENV_FILE"

echo
echo "===== HEALTH ====="
curl -fsS --max-time 10 http://127.0.0.1:8787/health
echo

echo
echo "===== CONDITIONAL LIVE EXECUTION ONCE ====="
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$LIVE_APP"
"/opt/kalman/.venv/bin/python" -m engine.r5_conditional_live
RC=$?
echo "conditional_live_rc=$RC"

"/opt/kalman/.venv/bin/python" -m engine.trade_mirror
MIRROR_RC=$?
echo "trade_mirror_rc=$MIRROR_RC"

echo
echo "R5_CONDITIONAL_LIVE_20000_APPLIED"
echo "normal=RANK1_20000"
echo "close_gap=RANK1_10000_PLUS_RANK2_10000"
echo "low_confidence=RANK1_10000_PLUS_CASH_10000"
echo "pyramiding=DISABLED"
echo "gap_threshold=$GAP_THRESHOLD"
echo "confidence_threshold=$CONF_THRESHOLD"

if [ "$RC" -ne 0 ]; then
  exit "$RC"
fi
exit "$MIRROR_RC"
