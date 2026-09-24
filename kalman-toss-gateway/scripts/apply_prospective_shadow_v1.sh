#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

SOURCE_ROOT="${KALMAN_SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TARGET_ROOT="${KALMAN_TARGET_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
ENABLE="${PROSPECTIVE_SHADOW_APPLY_ENABLE:-false}"
BASE_REF="${PROSPECTIVE_SHADOW_BASE_REF:-origin/main}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="/opt/kalman/backups/prospective-shadow-$STAMP"

RUNTIME_FILES=(
  "app/prospective_shadow.py"
  "engine/prospective_shadow.py"
  "engine/position_manager.py"
  "scripts/run_position_watch.sh"
  "scripts/run_execution_watch.sh"
  "scripts/run_auto_trade.sh"
  "scripts/configure_prospective_shadow_env.sh"
  "scripts/prospective_shadow_status.sh"
)

DOC_FILES=(
  "research/quant_stack/live_policy_no_profit_flip_v1.json"
  "docs/LIVE_POLICY_NO_PROFIT_FLIP_V1.md"
)

MODIFIED_EXISTING=(
  "engine/position_manager.py"
  "scripts/run_position_watch.sh"
  "scripts/run_execution_watch.sh"
  "scripts/run_auto_trade.sh"
)

echo "===================================================="
echo "APPLY PROSPECTIVE SHADOW V1"
echo "===================================================="
echo "source_root=$SOURCE_ROOT"
echo "target_root=$TARGET_ROOT"
echo "env_file=$ENV_FILE"
echo "enable=$ENABLE"
echo "base_ref=$BASE_REF"

if [[ "$ENABLE" != "true" && "$ENABLE" != "false" ]]; then
  echo "[FAIL] PROSPECTIVE_SHADOW_APPLY_ENABLE must be true or false"
  exit 2
fi

GIT_ROOT="$(git -C "$SOURCE_ROOT" rev-parse --show-toplevel 2>/dev/null)"
GIT_RC=$?
if [[ $GIT_RC -ne 0 || -z "$GIT_ROOT" ]]; then
  echo "[FAIL] source_root is not inside a git worktree: $SOURCE_ROOT"
  exit 2
fi
echo "git_root=$GIT_ROOT"

if [[ ! -d "$TARGET_ROOT" ]]; then
  echo "[FAIL] target_root missing: $TARGET_ROOT"
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] env file missing: $ENV_FILE"
  exit 2
fi

for rel in "${RUNTIME_FILES[@]}" "${DOC_FILES[@]}"; do
  if [[ ! -f "$SOURCE_ROOT/$rel" ]]; then
    echo "[FAIL] source file missing: $SOURCE_ROOT/$rel"
    exit 2
  fi
done

echo
echo "===== SOURCE SYNTAX ====="
"$PY" -m py_compile   "$SOURCE_ROOT/app/prospective_shadow.py"   "$SOURCE_ROOT/engine/prospective_shadow.py"   "$SOURCE_ROOT/engine/position_manager.py"
PY_RC=$?
echo "python_compile_rc=$PY_RC"
if [[ $PY_RC -ne 0 ]]; then
  exit "$PY_RC"
fi

for rel in   "scripts/run_position_watch.sh"   "scripts/run_execution_watch.sh"   "scripts/run_auto_trade.sh"   "scripts/configure_prospective_shadow_env.sh"   "scripts/prospective_shadow_status.sh"
do
  bash -n "$SOURCE_ROOT/$rel"
  RC=$?
  echo "bash_n_rc=$RC file=$rel"
  if [[ $RC -ne 0 ]]; then
    exit "$RC"
  fi
done

echo
echo "===== PRODUCTION DRIFT CHECK ====="
cd "$GIT_ROOT"
CD_RC=$?
if [[ $CD_RC -ne 0 ]]; then
  echo "[FAIL] cannot cd git_root"
  exit "$CD_RC"
fi

DRIFT=0
for rel in "${MODIFIED_EXISTING[@]}"; do
  if [[ ! -f "$TARGET_ROOT/$rel" ]]; then
    echo "[FAIL] production file missing: $TARGET_ROOT/$rel"
    DRIFT=1
    continue
  fi

  BASE_TMP="$(mktemp)"
  git show "$BASE_REF:kalman-toss-gateway/$rel" > "$BASE_TMP" 2>/dev/null
  SHOW_RC=$?
  if [[ $SHOW_RC -ne 0 ]]; then
    rm -f "$BASE_TMP"
    echo "[FAIL] cannot resolve base file: $BASE_REF:kalman-toss-gateway/$rel"
    DRIFT=1
    continue
  fi

  BASE_HASH="$(sha256sum "$BASE_TMP" | awk '{print $1}')"
  TARGET_HASH="$(sha256sum "$TARGET_ROOT/$rel" | awk '{print $1}')"
  rm -f "$BASE_TMP"

  if [[ "$TARGET_HASH" != "$BASE_HASH" ]]; then
    echo "[DRIFT] $rel"
    echo "  expected_main=$BASE_HASH"
    echo "  production=$TARGET_HASH"
    DRIFT=1
  else
    echo "[PASS] $rel matches $BASE_REF"
  fi
done

if [[ $DRIFT -ne 0 && "${ALLOW_PROSPECTIVE_SHADOW_PRODUCTION_DRIFT:-false}" != "true" ]]; then
  echo
  echo "[FAIL] production drift detected; no files changed"
  echo "Review the differences before applying."
  exit 3
fi

echo
echo "===== BACKUP ====="
mkdir -p "$BACKUP_ROOT"
MK_RC=$?
if [[ $MK_RC -ne 0 ]]; then
  echo "[FAIL] cannot create backup dir: $BACKUP_ROOT"
  exit "$MK_RC"
fi

for rel in "${RUNTIME_FILES[@]}" "${DOC_FILES[@]}"; do
  if [[ -f "$TARGET_ROOT/$rel" ]]; then
    mkdir -p "$BACKUP_ROOT/$(dirname "$rel")"
    cp -a "$TARGET_ROOT/$rel" "$BACKUP_ROOT/$rel"
  else
    mkdir -p "$BACKUP_ROOT/$(dirname "$rel")"
    : > "$BACKUP_ROOT/$rel.__NEW_FILE__"
  fi
done
cp -a "$ENV_FILE" "$BACKUP_ROOT/env.before"
echo "backup_root=$BACKUP_ROOT"

restore_files() {
  echo "[ROLLBACK] restoring prospective shadow files"
  for rel in "${RUNTIME_FILES[@]}" "${DOC_FILES[@]}"; do
    if [[ -f "$BACKUP_ROOT/$rel.__NEW_FILE__" ]]; then
      rm -f "$TARGET_ROOT/$rel"
    elif [[ -f "$BACKUP_ROOT/$rel" ]]; then
      mkdir -p "$TARGET_ROOT/$(dirname "$rel")"
      cp -a "$BACKUP_ROOT/$rel" "$TARGET_ROOT/$rel"
    fi
  done
  if [[ -f "$BACKUP_ROOT/env.before" ]]; then
    cp -a "$BACKUP_ROOT/env.before" "$ENV_FILE"
  fi
}

echo
echo "===== INSTALL ====="
for rel in "${RUNTIME_FILES[@]}" "${DOC_FILES[@]}"; do
  mkdir -p "$TARGET_ROOT/$(dirname "$rel")"
  if [[ "$rel" == scripts/* ]]; then
    install -m 0755 "$SOURCE_ROOT/$rel" "$TARGET_ROOT/$rel"
  else
    install -m 0644 "$SOURCE_ROOT/$rel" "$TARGET_ROOT/$rel"
  fi
  RC=$?
  echo "install_rc=$RC file=$rel"
  if [[ $RC -ne 0 ]]; then
    restore_files
    exit "$RC"
  fi
done

echo
echo "===== TARGET COMPILE ====="
"$PY" -m py_compile   "$TARGET_ROOT/app/prospective_shadow.py"   "$TARGET_ROOT/engine/prospective_shadow.py"   "$TARGET_ROOT/engine/position_manager.py"
TARGET_COMPILE_RC=$?
echo "target_compile_rc=$TARGET_COMPILE_RC"
if [[ $TARGET_COMPILE_RC -ne 0 ]]; then
  restore_files
  exit "$TARGET_COMPILE_RC"
fi

if [[ "$ENABLE" == "true" ]]; then
  echo
  echo "===== ENABLE FROZEN CANDIDATE ====="
  KALMAN_ENV_FILE="$ENV_FILE"     "$TARGET_ROOT/scripts/configure_prospective_shadow_env.sh" enable
  ENABLE_RC=$?
  echo "enable_rc=$ENABLE_RC"
  if [[ $ENABLE_RC -ne 0 ]]; then
    restore_files
    exit "$ENABLE_RC"
  fi
fi

echo
echo "===== INITIALIZE SHADOW SCHEMA ====="
PYTHONPATH="$TARGET_ROOT" KALMAN_ENV_FILE="$ENV_FILE" "$PY" - <<'PY'
import os
from dotenv import load_dotenv

load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)

from app.prospective_shadow import ProspectiveShadowConfig, ProspectiveShadowStore

config = ProspectiveShadowConfig.from_env()
state_db = os.environ.get("TRADING_STATE_DB", "/opt/kalman/state/trading.sqlite3")
store = ProspectiveShadowStore(state_db)
print(config.jsonable())
print(store.summary(config.candidate_id))
PY
SCHEMA_RC=$?
echo "schema_rc=$SCHEMA_RC"
if [[ $SCHEMA_RC -ne 0 ]]; then
  restore_files
  exit "$SCHEMA_RC"
fi

echo
echo "===== EXISTING GATEWAY HEALTH (NO RESTART) ====="
curl -fsS http://127.0.0.1:8787/health
HEALTH_RC=$?
echo
echo "health_rc=$HEALTH_RC"

echo
echo "===== PROSPECTIVE SHADOW STATUS ====="
KALMAN_ENV_FILE="$ENV_FILE"   "$TARGET_ROOT/scripts/prospective_shadow_status.sh"
STATUS_RC=$?
echo "status_rc=$STATUS_RC"

echo
echo "===================================================="
echo "APPLY RESULT"
echo "===================================================="
echo "backup_root=$BACKUP_ROOT"
echo "enabled=$ENABLE"
echo "cron_changed=false"
echo "gateway_restarted=false"
echo "live_policy_changed=false"
echo "broker_order_path_added=false"
echo "health_rc=$HEALTH_RC"
echo "status_rc=$STATUS_RC"

exit "$STATUS_RC"
