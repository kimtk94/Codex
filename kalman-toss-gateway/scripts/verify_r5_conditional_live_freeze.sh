#!/usr/bin/env bash
set -u

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

echo "===== R5.1 CONDITIONAL LIVE FREEZE VERIFY ====="

fail=0

check_file() {
  if [ -f "$1" ]; then
    echo "[PASS] file $1"
  else
    echo "[FAIL] missing $1"
    fail=1
  fi
}

for f in   "$APP_ROOT/engine/r5_conditional_policy.py"   "$APP_ROOT/engine/r5_conditional_live.py"   "$APP_ROOT/engine/auto_trade.py"   "$APP_ROOT/engine/position_manager.py"   "$APP_ROOT/app/readiness.py"   "$APP_ROOT/scripts/run_execution_watch.sh"
do
  check_file "$f"
done

echo
echo "===== STATIC SAFETY MARKERS ====="

grep -q 'CONDITIONAL_SCORE_MISSING_RANK1' "$APP_ROOT/engine/r5_conditional_live.py"   && echo "[PASS] rank1 fail-closed"   || { echo "[FAIL] rank1 fail-closed"; fail=1; }

grep -q 'CONDITIONAL_SCORE_MISSING_RANK2' "$APP_ROOT/engine/r5_conditional_live.py"   && echo "[PASS] rank2 fail-closed"   || { echo "[FAIL] rank2 fail-closed"; fail=1; }

grep -q 'FRIDAY_EXECUTION_AFTER_SAFE_DEADLINE' "$APP_ROOT/engine/auto_trade.py"   && echo "[PASS] Friday actual-execution gate"   || { echo "[FAIL] Friday actual-execution gate"; fail=1; }

grep -q 'risk_manager=COMPLETED' "$APP_ROOT/scripts/run_execution_watch.sh"   && echo "[PASS] risk manager survives US-cycle contention"   || { echo "[FAIL] watcher risk phase marker"; fail=1; }

echo
echo "===== ENV CONTRACT ====="

sudo env   KALMAN_ENV_FILE="$ENV_FILE"   "$PY" - <<'PY'
import os
from dotenv import dotenv_values

p = os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")
v = dotenv_values(p)

expected = {
    "AUTO_TRADE_SIGNAL_POLICY": "R5_LIVE_CONDITIONAL",
    "AUTO_TRADE_STRATEGY_VERSION": "R5.1_BASE_HGB",
    "AUTO_TRADE_EXECUTION_MODE": "LIVE",
    "AUTO_TRADE_ORDER_KRW": "20000",
    "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "1",
    "AUTO_TRADE_CONDITIONAL_GAP_THRESHOLD": "0.08156846590660159",
    "AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD": "0.00041106678948450823",
}

bad = False
for key, want in expected.items():
    got = str(v.get(key) or "")
    ok = got == want
    print(("[PASS]" if ok else "[FAIL]"), key, "=", got, "expected", want)
    bad = bad or not ok

raise SystemExit(1 if bad else 0)
PY
rc=$?
if [ "$rc" -ne 0 ]; then fail=1; fi

echo
echo "===== CONDITIONAL BRANCH TEST ====="

sudo env   PYTHONPATH="$APP_ROOT"   KALMAN_ENV_FILE="$ENV_FILE"   "$PY" - <<'PY'
import os
from dotenv import load_dotenv
from engine.r5_conditional_policy import decide

load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
gap=float(os.environ["AUTO_TRADE_CONDITIONAL_GAP_THRESHOLD"])
conf=float(os.environ["AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD"])

cases=[
 ("LOW_CONFIDENCE", conf*0.8, conf*0.7, "LOW_CONFIDENCE", (("AAA",10000),), 10000),
 ("CLOSE_GAP", 0.001, 0.00095, "CLOSE_GAP", (("AAA",10000),("BBB",10000)), 0),
 ("WIDE_GAP", 0.001, 0.0005, "TOP1_ONLY_WIDE_GAP", (("AAA",20000),), 0),
]
for name,r1,r2,regime,legs,cash in cases:
    d=decide(
        rank1_symbol="AAA", rank1_score=r1,
        rank2_symbol="BBB", rank2_score=r2,
        gap_threshold=gap, confidence_threshold=conf,
        total_krw=20000,
    )
    ok=(d.regime==regime and d.legs_krw==legs and d.cash_krw==cash)
    print(("[PASS]" if ok else "[FAIL]"), name, d.regime, d.legs_krw, d.cash_krw)
    if not ok:
        raise SystemExit(1)
PY
rc=$?
if [ "$rc" -ne 0 ]; then fail=1; fi

echo
echo "===== GATEWAY HEALTH ====="
if curl -fsS http://127.0.0.1:8787/health; then
  echo
  echo "[PASS] gateway health"
else
  echo
  echo "[FAIL] gateway health"
  fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "R5_1_CONDITIONAL_LIVE_FREEZE_VERIFY=PASS"
  exit 0
fi

echo "R5_1_CONDITIONAL_LIVE_FREEZE_VERIFY=FAIL"
exit 1
