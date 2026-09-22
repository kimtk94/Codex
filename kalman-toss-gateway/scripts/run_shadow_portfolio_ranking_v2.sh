#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PROD_VENV:-/opt/kalman/.venv}/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
CONFIG="${KALMAN_SHADOW_RANKING_CONFIG:-$APP_ROOT/config/shadow-portfolio-ranking-v2.json}"

MIRROR_NEON=false

usage() {
  cat <<'EOF'
Usage:
  run_shadow_portfolio_ranking_v2.sh [--mirror-neon]

Computes A/B/C SHADOW portfolio ranking from Market Data V2:
  A_EQUAL_WEIGHT
  B_STATIC_MAX_SHARPE
  C_RISK_CAP_110

Default is file output + Neon dry-run validation.
--mirror-neon mirrors only to shadow_portfolio_snapshot using a temporary gated env.

This runner does not call Toss, does not write strategy_signal/dashboard_snapshot,
and does not change production trading/model gates.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mirror-neon) MIRROR_NEON=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

fail(){ echo "[FAIL] $*" >&2; exit 1; }
[ -x "$PY" ] || fail "Python missing: $PY"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -f "$CONFIG" ] || fail "config missing: $CONFIG"
[ -f "$APP_ROOT/engine/shadow_portfolio_ranking.py" ] || fail "ranking engine missing"
[ -f "$APP_ROOT/engine/shadow_portfolio_ranking_writer.py" ] || fail "ranking writer missing"

mkdir -p "$LOCK_DIR"
exec 9>"$LOCK_DIR/shadow-portfolio-ranking-v2.lock"
flock -n 9 || fail "SHADOW portfolio ranking already running"

export KALMAN_ENV_FILE="$ENV_FILE"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

readarray -t PATHS < <("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys
v=dotenv_values(Path(sys.argv[1]))
root=v.get("KALMAN_DATA_ROOT") or "/opt/kalman/data"
market=v.get("KALMAN_MARKET_V2_OUTPUT_DIR") or f"{root}/Market_Data/v2"
model=v.get("KALMAN_MODEL_V2_ROOT") or f"{root}/Market_Model_V2"
output=v.get("KALMAN_SHADOW_RANKING_OUTPUT_DIR") or f"{model}/shadow_portfolio"
print(market)
print(output)
PY
)
MARKET_ROOT="${PATHS[0]}"
OUTPUT_ROOT="${PATHS[1]}"
RANKING_FILE="$OUTPUT_ROOT/latest/ranking.json"
STATUS_FILE="$OUTPUT_ROOT/latest/neon_mirror_status.json"

if [[ "$MARKET_ROOT" == /mnt/gdrive* || "$OUTPUT_ROOT" == /mnt/gdrive* ]]; then
  mountpoint -q /mnt/gdrive || fail "Google Drive mount unavailable"
  timeout 20 ls /mnt/gdrive >/dev/null || fail "Google Drive mount unreadable"
fi

CODE_SHA="${KALMAN_CODE_SHA:-unknown}"
if [ "$CODE_SHA" = "unknown" ] && command -v git >/dev/null 2>&1; then
  CODE_SHA="$(git -C "$APP_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
fi

echo "=================================================="
echo "Kalman SHADOW Portfolio Ranking V2"
echo "=================================================="
echo "Market root : $MARKET_ROOT"
echo "Output root : $OUTPUT_ROOT"
echo "Config      : $CONFIG"
echo "Code SHA    : $CODE_SHA"
echo "Neon mirror : $MIRROR_NEON"
echo

echo "[1/3] Compute A/B/C ranking"
"$PY" -m engine.shadow_portfolio_ranking   --market-root "$MARKET_ROOT"   --config "$CONFIG"   --output-dir "$OUTPUT_ROOT"   --code-sha "$CODE_SHA"

[ -s "$RANKING_FILE" ] || fail "ranking output missing: $RANKING_FILE"

echo
echo "[2/3] Validate Neon payload (dry-run)"
"$PY" -m engine.shadow_portfolio_ranking_writer   --ranking-file "$RANKING_FILE"   --status-file "$STATUS_FILE"   --dry-run

if [ "$MIRROR_NEON" = true ]; then
  echo
  echo "[3/3] Mirror ranking to isolated Neon table"

  TMP_ENV="$(mktemp /opt/kalman/.env.shadow-ranking.XXXXXX)"
  chmod 600 "$TMP_ENV"

  cleanup() {
    if [ -f "$TMP_ENV" ]; then
      if command -v shred >/dev/null 2>&1; then
        shred -u "$TMP_ENV"
      else
        rm -f "$TMP_ENV"
      fi
    fi
  }
  trap cleanup EXIT

  "$PY" - "$ENV_FILE" "$TMP_ENV" <<'PY'
from pathlib import Path
import sys

src=Path(sys.argv[1])
dst=Path(sys.argv[2])
remove={
    "KALMAN_SHADOW_RANKING_NEON_ENABLED",
    "KALMAN_SHADOW_RANKING_NEON_CONFIRM",
}
out=[]
for line in src.read_text(encoding="utf-8").splitlines():
    key=line.split("=",1)[0].strip() if "=" in line else ""
    if key not in remove:
        out.append(line)
out += [
    "KALMAN_SHADOW_RANKING_NEON_ENABLED=true",
    "KALMAN_SHADOW_RANKING_NEON_CONFIRM=CONFIRM_SHADOW_RANKING_MIRROR",
]
dst.write_text("\n".join(out).rstrip()+"\n",encoding="utf-8")
dst.chmod(0o600)
PY

  KALMAN_ENV_FILE="$TMP_ENV" "$PY" -m engine.shadow_portfolio_ranking_writer     --ranking-file "$RANKING_FILE"     --status-file "$STATUS_FILE"

  cleanup
  trap - EXIT
else
  echo
  echo "[3/3] Neon mirror skipped"
fi

echo
"$PY" - "$RANKING_FILE" "$STATUS_FILE" <<'PY'
import json,sys
from pathlib import Path
ranking=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
status=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
print("ranking_status :", ranking.get("status"))
print("tracking_status:", ranking.get("tracking_status"))
print("data_as_of     :", ranking.get("data_as_of"))
print("post_seed_rows :", ranking.get("post_seed_return_rows"))
for row in ranking.get("forward_ranking") or []:
    print(
        f"rank={row.get('forward_rank')} eligible={row.get('rank_eligible')} "
        f"{row.get('strategy')}: return={row.get('total_return')} "
        f"sharpe={row.get('sharpe')} mdd={row.get('max_drawdown')} "
        f"obs={row.get('observations')} rebalances={row.get('rebalance_count')} "
        f"target={row.get('latest_target')}"
    )
cap = ranking.get("risk_cap_audit_latest") or {}
if cap:
    print(
        "risk_cap_latest:",
        f"binding={cap.get('risk_cap_binding')}",
        f"reason={cap.get('risk_cap_reason')}",
        f"ew_vol={cap.get('equal_weight_vol')}",
        f"max_sharpe_vol={cap.get('max_sharpe_vol')}",
        f"cap_vol={cap.get('risk_cap_vol')}",
        f"blended_vol={cap.get('blended_vol')}",
        f"alpha={cap.get('alpha_max_sharpe')}",
    )
print("neon_status    :", status.get("status"))
print("trade_execution:", status.get("trade_execution"))
PY

echo
echo "SHADOW_PORTFOLIO_RANKING_V2_COMPLETE"
