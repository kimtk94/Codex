#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
UNIT="kalman-shadow-bakeoff-v1"

[ -d "$APP_ROOT" ] || { echo "[FAIL] app missing: $APP_ROOT" >&2; exit 10; }
[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 11; }

# Do not start a second heavy job.
if systemctl is-active --quiet "$UNIT.service" 2>/dev/null; then
  echo "SHADOW_BAKEOFF_ALREADY_RUNNING"
  systemctl status "$UNIT.service" --no-pager || true
  exit 0
fi

# Conservative defaults. Override only after observing server headroom.
MEMORY_MAX="${KALMAN_SHADOW_BAKEOFF_MEMORY_MAX:-1024M}"
CPU_QUOTA="${KALMAN_SHADOW_BAKEOFF_CPU_QUOTA:-50%}"
TIMEOUT_SEC="${KALMAN_SHADOW_BAKEOFF_TIMEOUT_SEC:-5400}"

echo "============================================================"
echo "Kalman guarded SHADOW bake-off"
echo "============================================================"
echo "MemoryMax : $MEMORY_MAX"
echo "CPUQuota  : $CPU_QUOTA"
echo "Timeout   : $TIMEOUT_SEC sec"
echo

# systemd transient service isolates the research job from the rest of the server.
# If it exceeds MemoryMax, only this unit is killed by cgroup OOM policy.
exec systemd-run   --unit="$UNIT"   --collect   --property="MemoryMax=$MEMORY_MAX"   --property="MemorySwapMax=512M"   --property="CPUQuota=$CPU_QUOTA"   --property="Nice=10"   --property="IOSchedulingClass=best-effort"   --property="IOSchedulingPriority=7"   --property="TimeoutStartSec=$TIMEOUT_SEC"   --setenv="KALMAN_APP_ROOT=$APP_ROOT"   --setenv="KALMAN_ENV_FILE=$ENV_FILE"   /bin/bash "$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"
