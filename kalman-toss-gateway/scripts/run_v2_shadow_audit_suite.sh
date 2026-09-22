#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PROD_VENV:-/opt/kalman/.venv}/bin/python"

MIRROR_NEON=false
SKIP_FINVIZ=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mirror-neon) MIRROR_NEON=true ;;
    --skip-finviz) SKIP_FINVIZ=true ;;
    -h|--help)
      echo "Usage: run_v2_shadow_audit_suite.sh [--mirror-neon] [--skip-finviz]"
      exit 0
      ;;
    *) echo "[FAIL] unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -x "$PY" ] || { echo "[FAIL] Python missing: $PY" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

refresh_args=()
ranking_args=()
[ "$MIRROR_NEON" = true ] && refresh_args+=(--mirror-neon) && ranking_args+=(--mirror-neon)
[ "$SKIP_FINVIZ" = true ] && refresh_args+=(--skip-finviz)

echo "===== 1/3 FIXED MODEL SHADOW REFRESH ====="
"$APP_ROOT/scripts/run_v2_shadow_refresh.sh" "${refresh_args[@]}"

echo
echo "===== 2/3 A/B/C SHADOW PORTFOLIO ====="
"$APP_ROOT/scripts/run_shadow_portfolio_ranking_v2.sh" "${ranking_args[@]}"

echo
echo "===== 3/3 CONSOLIDATED AUDIT ====="
"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import json
import sys

env = dotenv_values(Path(sys.argv[1]))
root = env.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
feature_root = Path(env.get("KALMAN_FEATURES_V2_OUTPUT_DIR") or f"{root}/Market_Features/v2")
model_root = Path(env.get("KALMAN_MODEL_V2_ROOT") or f"{root}/Market_Model_V2")
ranking_root = Path(env.get("KALMAN_SHADOW_RANKING_OUTPUT_DIR") or f"{model_root}/shadow_portfolio")

feature_status = json.loads((feature_root / "features_v2_run_status.json").read_text())
shadow_status = json.loads((model_root / "shadow/shadow_run_status.json").read_text())
ranking = json.loads((ranking_root / "latest/ranking.json").read_text())

print("FEATURE STATUS:", feature_status.get("status"))
vix = ((feature_status.get("assets") or {}).get("yf_vix") or {})
vix_cmp = vix.get("legacy_rsi_comparison") or {}
print(
    "VIX RSI:",
    "status=", vix_cmp.get("status"),
    "close_valid=", vix_cmp.get("close_valid_rows"),
    "legacy_valid=", vix_cmp.get("legacy_valid_rows"),
    "talib_valid=", vix_cmp.get("talib_valid_rows"),
    "timestamp_overlap=", vix_cmp.get("timestamp_overlap_rows"),
    "overlap=", vix_cmp.get("overlap_rows"),
    "reason=", vix_cmp.get("reason"),
)

print("\nSHADOW SIGNALS")
for market, row in (shadow_status.get("markets") or {}).items():
    cal = row.get("calibration") or {}
    print(
        market,
        "direction=", row.get("shadow_direction"),
        "p_up=", row.get("probability_up"),
        "quality=", row.get("data_quality"),
        "calibration=", cal.get("status"),
        "cal_rows=", cal.get("rows"),
        "brier=", cal.get("brier"),
        "log_loss=", cal.get("log_loss"),
        "ece=", cal.get("ece_10bin"),
    )

print("\nPORTFOLIO")
print("tracking_status=", ranking.get("tracking_status"))
print("post_seed_rows=", ranking.get("post_seed_return_rows"))
for row in ranking.get("forward_ranking") or []:
    print(
        row.get("strategy"),
        "rank=", row.get("forward_rank"),
        "eligible=", row.get("rank_eligible"),
        "obs=", row.get("observations"),
        "rebalances=", row.get("rebalance_count"),
        "return=", row.get("total_return"),
        "sharpe=", row.get("sharpe"),
        "mdd=", row.get("max_drawdown"),
    )

cap = ranking.get("risk_cap_audit_latest") or {}
print(
    "risk_cap:",
    "binding=", cap.get("risk_cap_binding"),
    "reason=", cap.get("risk_cap_reason"),
    "ew_vol=", cap.get("equal_weight_vol"),
    "max_sharpe_vol=", cap.get("max_sharpe_vol"),
    "cap_vol=", cap.get("risk_cap_vol"),
    "blended_vol=", cap.get("blended_vol"),
    "alpha=", cap.get("alpha_max_sharpe"),
)

invariants = ranking.get("invariants") or {}
for key in (
    "entry_allowed_for_real_orders",
    "auto_trade_visible",
    "production_model_write",
    "strategy_signal_write",
    "dashboard_snapshot_write",
    "toss_execution",
    "live_execution",
    "trade_execution",
):
    if invariants.get(key) is not False:
        raise SystemExit(f"[FAIL] safety invariant {key}={invariants.get(key)!r}")
if invariants.get("research_only") is not True:
    raise SystemExit("[FAIL] safety invariant research_only must be true")
print("\nSAFETY INVARIANTS: PASS")
PY

echo
echo "V2_SHADOW_AUDIT_SUITE_COMPLETE"
