#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"
LOCK_DIR="${KALMAN_LOCK_DIR:-/opt/kalman/state}"
RCLONE_CONFIG="${KALMAN_RCLONE_CONFIG:-/etc/rclone/rclone.conf}"
RCLONE_REMOTE="${KALMAN_GDRIVE_REMOTE:-gdrive:}"
WORK_ROOT="${KALMAN_HISTORICAL_REFRESH_WORK_ROOT:-/var/tmp/kalman-historical-refresh}"

RAW_REMOTE="${KALMAN_HISTORICAL_RAW_REMOTE:-${RCLONE_REMOTE}Market_Data/v2/raw/historical_2017/multimarket_raw_2017_present.parquet}"
FEATURE_REMOTE="${KALMAN_HISTORICAL_FEATURE_REMOTE:-${RCLONE_REMOTE}Market_Features/v2/talib/historical_2017/multimarket_features_2017_present_v0_3.parquet}"
MARKET_REMOTE_ROOT="${KALMAN_MARKET_V2_REMOTE_ROOT:-${RCLONE_REMOTE}Market_Data/v2}"
BACKUP_REMOTE_ROOT="${KALMAN_HISTORICAL_BACKUP_REMOTE_ROOT:-${RCLONE_REMOTE}Market_Data/v2/raw/historical_2017/_refresh_backups}"
STATUS_REMOTE="${KALMAN_HISTORICAL_STATUS_REMOTE:-${RCLONE_REMOTE}Market_Model_V2/shadow_bakeoff/v1/latest/historical_source_refresh.json}"
MAPPING="${KALMAN_HISTORICAL_REFRESH_MAPPING:-$APP_ROOT/config/historical-source-refresh-v1.json}"

PARITY_MIN="${KALMAN_HISTORICAL_REFRESH_PARITY_MIN_POINTS:-30}"
PARITY_MAX="${KALMAN_HISTORICAL_REFRESH_MAX_PARITY_ERROR:-0.03}"
OVERLAP_MIN="${KALMAN_HISTORICAL_REFRESH_SOURCE_OVERLAP_MIN_POINTS:-5}"
OVERLAP_MAX="${KALMAN_HISTORICAL_REFRESH_MAX_SOURCE_CLOSE_REL_ERROR:-0.01}"
BW_LIMIT="${KALMAN_HISTORICAL_REFRESH_BWLIMIT:-20M}"

need_file() {
  [ -f "$1" ] || {
    echo "[FAIL] missing file: $1" >&2
    return 1
  }
}

need_exec() {
  [ -x "$1" ] || {
    echo "[FAIL] missing executable: $1" >&2
    return 1
  }
}

need_exec "$PY"
need_file "$ENV_FILE"
need_file "$RCLONE_CONFIG"
need_file "$MAPPING"
command -v rclone >/dev/null 2>&1 || {
  echo "[FAIL] rclone not found" >&2
  exit 10
}

mkdir -p "$LOCK_DIR" "$WORK_ROOT"
exec 9>"$LOCK_DIR/historical-source-refresh-rclone.lock"
flock -n 9 || {
  echo "HISTORICAL_SOURCE_REFRESH_RCLONE_ALREADY_RUNNING" >&2
  exit 40
}

"$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
from dotenv import dotenv_values
import sys

v = dotenv_values(Path(sys.argv[1]))
trading = str(v.get("TRADING_ENABLED") or "").strip().lower()
confirm = str(v.get("LIVE_TRADING_CONFIRM") or "").strip()
auto = str(v.get("AUTO_TRADE_ENABLED") or "").strip().lower()
mode = str(v.get("AUTO_TRADE_EXECUTION_MODE") or "DRY_RUN").strip().upper()

print("TRADING_ENABLED          =", trading or "(empty)")
print("LIVE_TRADING_CONFIRM     =", "SET" if confirm else "(empty)")
print("AUTO_TRADE_ENABLED       =", auto or "(empty)")
print("AUTO_TRADE_EXECUTION_MODE=", mode)

if trading == "true":
    raise SystemExit("[FAIL] TRADING_ENABLED=true")
if confirm:
    raise SystemExit("[FAIL] LIVE_TRADING_CONFIRM is set")
if auto == "true":
    raise SystemExit("[FAIL] AUTO_TRADE_ENABLED=true")
if mode != "DRY_RUN":
    raise SystemExit(f"[FAIL] AUTO_TRADE_EXECUTION_MODE={mode}")
PY

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$WORK_ROOT/$RUN_ID"
MARKET="$WORK/market"
BACKUPS="$WORK/backups"
RECHECK="$WORK/recheck"
VERIFY="$WORK/verify"
STATUS="$WORK/historical_source_refresh.json"

RAW="$WORK/multimarket_raw_2017_present.parquet"
FEATURES="$WORK/multimarket_features_2017_present_v0_3.parquet"
RAW_ORIG="$WORK/original_raw.parquet"
FEATURE_ORIG="$WORK/original_features.parquet"

mkdir -p "$MARKET/raw/yfinance" "$MARKET/raw/financedatareader" "$BACKUPS" "$RECHECK" "$VERIFY"

RCLONE=(rclone --config "$RCLONE_CONFIG" --transfers 1 --checkers 1 --bwlimit "$BW_LIMIT")

echo "============================================================"
echo "Kalman Historical Source Refresh — rclone guarded"
echo "============================================================"
echo "run_id       : $RUN_ID"
echo "raw_remote   : $RAW_REMOTE"
echo "feature_remote: $FEATURE_REMOTE"
echo "mapping      : $MAPPING"
echo "live/toss    : FALSE"
echo "neon/prod    : FALSE"
echo

echo "[1/7] Stage canonical historical pair"
"${RCLONE[@]}" copyto "$RAW_REMOTE" "$RAW"
"${RCLONE[@]}" copyto "$FEATURE_REMOTE" "$FEATURES"
cp -p "$RAW" "$RAW_ORIG"
cp -p "$FEATURES" "$FEATURE_ORIG"

RAW_BASE_SHA="$(sha256sum "$RAW_ORIG" | awk '{print $1}')"
FEATURE_BASE_SHA="$(sha256sum "$FEATURE_ORIG" | awk '{print $1}')"
echo "raw_baseline_sha256=$RAW_BASE_SHA"
echo "feature_baseline_sha256=$FEATURE_BASE_SHA"

copy_current() {
  local rel="$1"
  local dest="$MARKET/$rel"
  mkdir -p "$(dirname "$dest")"
  if "${RCLONE[@]}" copyto "$MARKET_REMOTE_ROOT/$rel" "$dest" >/dev/null 2>&1; then
    echo "CURRENT_SOURCE=FOUND $rel"
    return 0
  fi
  rm -f "$dest"
  echo "CURRENT_SOURCE=MISSING $rel"
  return 0
}

echo "[2/7] Stage current source snapshots"
for rel in   raw/yfinance/yf_spy.parquet   raw/yfinance/yf_qqq.parquet   raw/yfinance/yf_soxx.parquet   raw/yfinance/yf_iwm.parquet   raw/yfinance/yf_gld.parquet   raw/yfinance/yf_hyg.parquet   raw/yfinance/yf_lqd.parquet   raw/yfinance/yf_btc.parquet   raw/financedatareader/fdr_kospi.parquet   raw/yfinance/yf_kospi.parquet   raw/financedatareader/fdr_kosdaq.parquet   raw/yfinance/yf_kosdaq.parquet
do
  copy_current "$rel"
done

echo "[3/7] Apply refresh to local staged pair"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$APP_ROOT"

"$PY" -m research.shadow_bakeoff.historical_source_refresh   --raw "$RAW"   --features "$FEATURES"   --market-root "$MARKET"   --mapping "$MAPPING"   --output-status "$STATUS"   --backup-root "$BACKUPS"   --parity-min-points "$PARITY_MIN"   --max-parity-error "$PARITY_MAX"   --source-overlap-min-points "$OVERLAP_MIN"   --max-source-close-relative-error "$OVERLAP_MAX"   --apply

readarray -t RESULT < <("$PY" - "$STATUS" <<'PY'
import json
import sys
from pathlib import Path

x = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if x.get("status") != "READY":
    raise SystemExit(f"[FAIL] status={x.get('status')}")
if x.get("research_only") is not True:
    raise SystemExit("[FAIL] research_only invariant")
for key in ("live_execution", "toss_execution", "neon_write", "production_write"):
    if x.get(key) is not False:
        raise SystemExit(f"[FAIL] invariant {key}={x.get(key)!r}")
write_status = str(x.get("write_status") or "")
if write_status not in {"APPLIED", "NO_CHANGES"}:
    raise SystemExit(f"[FAIL] write_status={write_status}")
print(write_status)
print(int(x.get("new_raw_rows") or 0))
print(int(x.get("new_feature_rows") or 0))
PY
)

WRITE_STATUS="${RESULT[0]}"
NEW_RAW="${RESULT[1]}"
NEW_FEATURES="${RESULT[2]}"
echo "write_status=$WRITE_STATUS"
echo "new_raw_rows=$NEW_RAW"
echo "new_feature_rows=$NEW_FEATURES"

if [ "$WRITE_STATUS" = "NO_CHANGES" ]; then
  echo "[4/7] No historical changes to promote"
  "${RCLONE[@]}" copyto "$STATUS" "$STATUS_REMOTE"
  echo "HISTORICAL_SOURCE_REFRESH_RCLONE_COMPLETE"
  exit 0
fi

echo "[4/7] Recheck remote canonical pair for concurrent changes"
"${RCLONE[@]}" copyto "$RAW_REMOTE" "$RECHECK/raw.parquet"
"${RCLONE[@]}" copyto "$FEATURE_REMOTE" "$RECHECK/features.parquet"

RAW_RECHECK_SHA="$(sha256sum "$RECHECK/raw.parquet" | awk '{print $1}')"
FEATURE_RECHECK_SHA="$(sha256sum "$RECHECK/features.parquet" | awk '{print $1}')"

if [ "$RAW_RECHECK_SHA" != "$RAW_BASE_SHA" ] || [ "$FEATURE_RECHECK_SHA" != "$FEATURE_BASE_SHA" ]; then
  echo "[FAIL] remote canonical pair changed during refresh; refusing promotion" >&2
  exit 50
fi

RAW_NEW_SHA="$(sha256sum "$RAW" | awk '{print $1}')"
FEATURE_NEW_SHA="$(sha256sum "$FEATURES" | awk '{print $1}')"

echo "[5/7] Persist rollback copies"
REMOTE_BACKUP_DIR="$BACKUP_REMOTE_ROOT/$RUN_ID"
"${RCLONE[@]}" copyto "$RAW_ORIG" "$REMOTE_BACKUP_DIR/multimarket_raw_2017_present.parquet"
"${RCLONE[@]}" copyto "$FEATURE_ORIG" "$REMOTE_BACKUP_DIR/multimarket_features_2017_present_v0_3.parquet"

restore_pair() {
  echo "[ROLLBACK] restoring remote canonical pair" >&2
  "${RCLONE[@]}" copyto "$RAW_ORIG" "$RAW_REMOTE" || true
  "${RCLONE[@]}" copyto "$FEATURE_ORIG" "$FEATURE_REMOTE" || true
}

echo "[6/7] Promote refreshed pair with verification"
if ! "${RCLONE[@]}" copyto "$RAW" "$RAW_REMOTE"; then
  restore_pair
  exit 60
fi
if ! "${RCLONE[@]}" copyto "$FEATURES" "$FEATURE_REMOTE"; then
  restore_pair
  exit 61
fi

if ! "${RCLONE[@]}" copyto "$RAW_REMOTE" "$VERIFY/raw.parquet"; then
  restore_pair
  exit 62
fi
if ! "${RCLONE[@]}" copyto "$FEATURE_REMOTE" "$VERIFY/features.parquet"; then
  restore_pair
  exit 63
fi

RAW_VERIFY_SHA="$(sha256sum "$VERIFY/raw.parquet" | awk '{print $1}')"
FEATURE_VERIFY_SHA="$(sha256sum "$VERIFY/features.parquet" | awk '{print $1}')"

if [ "$RAW_VERIFY_SHA" != "$RAW_NEW_SHA" ] || [ "$FEATURE_VERIFY_SHA" != "$FEATURE_NEW_SHA" ]; then
  echo "[FAIL] remote verification hash mismatch" >&2
  restore_pair
  exit 64
fi

echo "[7/7] Publish refresh status"
"${RCLONE[@]}" copyto "$STATUS" "$STATUS_REMOTE"

echo "raw_remote_sha256=$RAW_VERIFY_SHA"
echo "feature_remote_sha256=$FEATURE_VERIFY_SHA"
echo "backup_remote=$REMOTE_BACKUP_DIR"
echo "HISTORICAL_SOURCE_REFRESH_RCLONE_COMPLETE"
