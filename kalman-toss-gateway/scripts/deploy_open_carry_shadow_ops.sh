#!/usr/bin/env bash
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo from the checked-out worktree:" >&2
  echo "  sudo bash kalman-toss-gateway/scripts/deploy_open_carry_shadow_ops.sh" >&2
  exit 1
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
STATE_DIR="${KALMAN_STATE_DIR:-/opt/kalman/state}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$STATE_DIR/open-carry-shadow-ops-backup-$STAMP"
MIRROR_DIR="${OPEN_CARRY_SHADOW_MIRROR_DIR:-/home/taehoon/kalman-data/trading}"
MIRROR_PATH="$MIRROR_DIR/open-carry-shadow-latest.json"
READINESS_PATH="$MIRROR_DIR/open-carry-readiness.json"

fail() { echo "[FAIL] $*" >&2; exit 1; }

[ -x "$PY" ] || fail "Python missing/not executable: $PY"
[ -f "$ENV_FILE" ] || fail "env missing: $ENV_FILE"
[ -f "$SRC_ROOT/engine/open_carry_shadow.py" ] || fail "source shadow module missing"
[ -f "$SRC_ROOT/scripts/probe_open_carry_readiness.py" ] || fail "readiness probe missing"

echo "[1/5] Backup current shadow module"
install -d -m 0750 "$BACKUP_DIR"
if [ -f "$APP_ROOT/engine/open_carry_shadow.py" ]; then
  install -D -m 0644 "$APP_ROOT/engine/open_carry_shadow.py" "$BACKUP_DIR/engine/open_carry_shadow.py"
fi

echo "[2/5] Install shadow observability only"
install -m 0644 "$SRC_ROOT/engine/open_carry_shadow.py" "$APP_ROOT/engine/open_carry_shadow.py"
install -m 0755 "$SRC_ROOT/scripts/probe_open_carry_readiness.py" "$APP_ROOT/scripts/probe_open_carry_readiness.py"
PYTHONPATH="$APP_ROOT" "$PY" -m py_compile "$APP_ROOT/engine/open_carry_shadow.py" "$APP_ROOT/scripts/probe_open_carry_readiness.py" || fail "py_compile failed"

echo "[3/5] Mirror any existing shadow state"
install -d -m 0755 "$MIRROR_DIR"
if [ -f "$STATE_DIR/open_carry_shadow.json" ]; then
  install -m 0644 "$STATE_DIR/open_carry_shadow.json" "$MIRROR_PATH"
  echo "[INFO] existing_shadow_state_mirrored=$MIRROR_PATH"
else
  echo "[INFO] no_existing_shadow_state"
fi

echo "[4/5] Write sanitized readiness report"
KALMAN_ENV_FILE="$ENV_FILE" KALMAN_APP_ROOT="$APP_ROOT" PYTHONPATH="$APP_ROOT" \
  "$PY" "$APP_ROOT/scripts/probe_open_carry_readiness.py" \
  --env-file "$ENV_FILE" --app-root "$APP_ROOT" | tee "$READINESS_PATH"
PROBE_RC=${PIPESTATUS[0]}
chmod 0644 "$READINESS_PATH" 2>/dev/null || true
chmod 0644 "$MIRROR_PATH" 2>/dev/null || true
if [ -n "${SUDO_USER:-}" ]; then
  chown -R "$SUDO_USER":"$SUDO_USER" "$MIRROR_DIR" 2>/dev/null || true
fi

echo "[5/5] Safety boundary"
echo "[INFO] env_not_modified=true"
echo "[INFO] live_order_module_not_modified=true"
echo "[INFO] auto_trade_not_modified=true"
echo "[INFO] open_carry_live_not_enabled_by_this_script=true"
echo "[INFO] backup=$BACKUP_DIR"
echo "[INFO] readiness=$READINESS_PATH"
echo "[INFO] shadow_mirror=$MIRROR_PATH"

exit "$PROBE_RC"
