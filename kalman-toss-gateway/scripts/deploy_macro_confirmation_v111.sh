#!/usr/bin/env bash
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo from the checked-out worktree:" >&2
  echo "  sudo bash kalman-toss-gateway/scripts/deploy_macro_confirmation_v111.sh" >&2
  exit 1
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE_DIR="${KALMAN_STATE_DIR:-/opt/kalman/state}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$STATE_DIR/macro-confirmation-v111-backup-$STAMP"

fail() { echo "[FAIL] $*" >&2; exit 1; }

[ -x "$PY" ] || fail "Python missing/not executable: $PY"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"

FILES=(
  "engine/macro_event_features_v1.py"
  "engine/macro_equity_confirmation_v1.py"
  "engine/macro_intraday_us2y_provider_v1.py"
  "config/macro-event-features-v1.json"
  "scripts/probe_macro_intraday_us2y_v1.sh"
)

echo "[1/6] Validate source files"
for rel in "${FILES[@]}"; do
  [ -f "$SRC_ROOT/$rel" ] || fail "source missing: $SRC_ROOT/$rel"
done

echo "[2/6] Prepare backup"
install -d -m 0750 "$STATE_DIR" "$BACKUP_DIR" || fail "backup directory create failed"
install -d -m 0755 "$APP_ROOT/engine" "$APP_ROOT/config" "$APP_ROOT/scripts" || fail "runtime directories unavailable"
for rel in "${FILES[@]}"; do
  if [ -f "$APP_ROOT/$rel" ]; then
    install -D -m 0644 "$APP_ROOT/$rel" "$BACKUP_DIR/$rel" || fail "backup failed: $rel"
  fi
done
echo "[INFO] backup=$BACKUP_DIR"

echo "[3/6] Install shadow macro confirmation v1.11"
install -m 0644 "$SRC_ROOT/engine/macro_event_features_v1.py" "$APP_ROOT/engine/macro_event_features_v1.py" || fail "install macro_event_features_v1.py"
install -m 0644 "$SRC_ROOT/engine/macro_equity_confirmation_v1.py" "$APP_ROOT/engine/macro_equity_confirmation_v1.py" || fail "install macro_equity_confirmation_v1.py"
install -m 0644 "$SRC_ROOT/engine/macro_intraday_us2y_provider_v1.py" "$APP_ROOT/engine/macro_intraday_us2y_provider_v1.py" || fail "install macro_intraday_us2y_provider_v1.py"
install -m 0644 "$SRC_ROOT/config/macro-event-features-v1.json" "$APP_ROOT/config/macro-event-features-v1.json" || fail "install macro config"
install -m 0755 "$SRC_ROOT/scripts/probe_macro_intraday_us2y_v1.sh" "$APP_ROOT/scripts/probe_macro_intraday_us2y_v1.sh" || fail "install probe script"

echo "[4/6] Compile + config contract"
PYTHONPATH="$APP_ROOT" "$PY" -m py_compile \
  "$APP_ROOT/engine/macro_event_features_v1.py" \
  "$APP_ROOT/engine/macro_equity_confirmation_v1.py" \
  "$APP_ROOT/engine/macro_intraday_us2y_provider_v1.py" || fail "py_compile failed"

"$PY" - <<'PY' || exit 1
import json
from pathlib import Path
p=Path("/opt/kalman/app/config/macro-event-features-v1.json")
cfg=json.loads(p.read_text())
assert cfg["version"] == "macro-event-feature-v1.11.0"
i=cfg["intraday_us2y"]
assert i["symbol"] == "USGG2YR:IND"
assert i["interval"] == "1m"
assert i["shadow_only"] is True
assert cfg["equity_confirmation"]["shadow_only"] is True
print("[PASS] macro-event-feature-v1.11.0 shadow contract")
PY

echo "[5/6] Existing macro selftest"
KALMAN_ENV_FILE="$ENV_FILE" KALMAN_APP_ROOT="$APP_ROOT" KALMAN_PYTHON="$PY" \
  "$APP_ROOT/scripts/run_macro_event_features_v1.sh" selftest || fail "macro selftest failed"

echo "[6/6] Read-only US2Y intraday entitlement probe"
PROBE_REPORT="${KALMAN_MACRO_PROBE_REPORT:-/home/taehoon/kalman-data/macro/us2y-intraday-probe.json}"
PROBE_REPORT_DIR="$(dirname "$PROBE_REPORT")"
install -d -m 0755 "$PROBE_REPORT_DIR" || fail "probe report directory create failed"

KALMAN_ENV_FILE="$ENV_FILE" KALMAN_APP_ROOT="$APP_ROOT" KALMAN_PYTHON="$PY" \
  "$APP_ROOT/scripts/probe_macro_intraday_us2y_v1.sh" | tee "$PROBE_REPORT"
PROBE_RC=${PIPESTATUS[0]}
chmod 0644 "$PROBE_REPORT" 2>/dev/null || true
if [ -n "${SUDO_USER:-}" ]; then
  chown "$SUDO_USER":"$SUDO_USER" "$PROBE_REPORT" 2>/dev/null || true
fi

echo
echo "===== RESULT ====="
echo "[INFO] sanitized_probe_report=$PROBE_REPORT"
if [ "$PROBE_RC" -eq 0 ]; then
  echo "[PASS] An intraday US2Y shadow source is available."
  echo "[INFO] The report identifies whether authenticated 1m API or public 5m chart fallback was used."
else
  echo "[WARN] US2Y intraday entitlement probe did not pass (rc=$PROBE_RC)."
  echo "[WARN] Macro v1.11 remains installed but intraday provider is fail-closed."
  echo "[WARN] DGS2 remains a DAILY_PROXY; no fake intraday substitution occurs."
fi
echo "[INFO] No R5.x, auto-trade, position-manager, or execution-watch files were modified."
echo "[INFO] backup=$BACKUP_DIR"

exit "$PROBE_RC"
