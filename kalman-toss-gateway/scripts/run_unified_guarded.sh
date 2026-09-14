#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"

case "$MODE" in
  KR_GLOBAL|KR|US|CRYPTO_GLOBAL|CRYPTO|GLOBAL) ;;
  *) echo "Usage: $0 {KR_GLOBAL|KR|US|CRYPTO_GLOBAL|CRYPTO|GLOBAL}" >&2; exit 2 ;;
esac

MEMORY_MAX="${KALMAN_UNIFIED_MEMORY_MAX:-3G}"
MEMORY_SWAP_MAX="${KALMAN_UNIFIED_SWAP_MAX:-1G}"
CPU_QUOTA="${KALMAN_UNIFIED_CPU_QUOTA:-150%}"
TIMEOUT_SEC="${KALMAN_UNIFIED_TIMEOUT_SEC:-7200}"

slug="$(printf '%s' "$MODE" | tr '[:upper:]_' '[:lower:]-')"
unit="kalman-unified-${slug}-$(date +%Y%m%d%H%M%S)"

echo "============================================================"
echo "Kalman Unified guarded pipeline"
echo "============================================================"
echo "mode       : $MODE"
echo "unit       : $unit"
echo "MemoryMax  : $MEMORY_MAX"
echo "SwapMax    : $MEMORY_SWAP_MAX"
echo "CPUQuota   : $CPU_QUOTA"
echo "Timeout    : $TIMEOUT_SEC"
echo

exec systemd-run   --unit="$unit"   --collect   --wait   --pipe   --property="MemoryMax=$MEMORY_MAX"   --property="MemorySwapMax=$MEMORY_SWAP_MAX"   --property="CPUQuota=$CPU_QUOTA"   --property="Nice=10"   --property="IOSchedulingClass=best-effort"   --property="IOSchedulingPriority=7"   --property="TimeoutStartSec=$TIMEOUT_SEC"   --setenv="KALMAN_APP_ROOT=$APP_ROOT"   --setenv="KALMAN_ENV_FILE=$ENV_FILE"   /bin/bash "$APP_ROOT/scripts/run_pipeline.sh" "$MODE"
