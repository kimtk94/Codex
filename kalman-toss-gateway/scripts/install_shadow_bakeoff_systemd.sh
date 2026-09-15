#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
RESEARCH_VENV="${KALMAN_RESEARCH_V2_VENV:-/opt/kalman/.venv-research-v2}"
PY="$RESEARCH_VENV/bin/python"
SERVICE_SRC="$APP_ROOT/config/kalman-shadow-bakeoff-daily.service"
TIMER_SRC="$APP_ROOT/config/kalman-shadow-bakeoff-daily.timer"
SERVICE_DST="/etc/systemd/system/kalman-shadow-bakeoff-daily.service"
TIMER_DST="/etc/systemd/system/kalman-shadow-bakeoff-daily.timer"
LEGACY_CRON="/etc/cron.d/kalman-shadow-bakeoff-v1"
ACTION="${1:---install}"

usage() {
  cat <<'EOF'
Usage:
  install_shadow_bakeoff_systemd.sh --install
  install_shadow_bakeoff_systemd.sh --remove
  install_shadow_bakeoff_systemd.sh --show
EOF
}

case "$ACTION" in
  --install|--remove|--show) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "[FAIL] unknown action: $ACTION" >&2; usage >&2; exit 2 ;;
esac

if [ "$ACTION" = "--show" ]; then
  systemctl status kalman-shadow-bakeoff-daily.timer --no-pager || true
  echo
  systemctl list-timers kalman-shadow-bakeoff-daily.timer --all --no-pager || true
  exit 0
fi

[ "$(id -u)" -eq 0 ] || {
  echo "[FAIL] must run as root" >&2
  exit 10
}

if [ "$ACTION" = "--remove" ]; then
  systemctl disable --now kalman-shadow-bakeoff-daily.timer >/dev/null 2>&1 || true
  rm -f "$SERVICE_DST" "$TIMER_DST"
  systemctl daemon-reload
  echo "REMOVED kalman-shadow-bakeoff-daily systemd units"
  exit 0
fi

for f in "$SERVICE_SRC" "$TIMER_SRC"   "$APP_ROOT/scripts/run_shadow_bakeoff_daily.sh"   "$APP_ROOT/scripts/run_historical_source_refresh_rclone.sh"   "$APP_ROOT/research/model_v2/build_historical_feature_matrix.py"   "$APP_ROOT/research/quant_stack/historical_v3_2_portfolio_validation.py"   "$APP_ROOT/research/shadow_bakeoff/runner.py"
do
  [ -f "$f" ] || {
    echo "[FAIL] missing required file: $f" >&2
    exit 11
  }
done

[ -x "$PY" ] || {
  echo "[FAIL] research Python missing: $PY" >&2
  exit 12
}

PYTHONPATH="$APP_ROOT" "$PY" - <<'PY'
from importlib.metadata import version
from packaging.version import Version

import scipy
from pypfopt import EfficientFrontier
import research.model_v2.build_historical_feature_matrix
import research.quant_stack.historical_v3_2_portfolio_validation
import research.shadow_bakeoff.runner

if Version(version("PyPortfolioOpt")) != Version("1.6.0"):
    raise SystemExit("[FAIL] PyPortfolioOpt runtime must be exactly 1.6.0")
if Version(scipy.__version__) >= Version("1.18"):
    raise SystemExit("[FAIL] scipy runtime must remain < 1.18")

print("SHADOW_SYSTEMD_RUNTIME_PREFLIGHT=PASS")
PY

if [ -f "$LEGACY_CRON" ]; then
  mv "$LEGACY_CRON" "$LEGACY_CRON.disabled.$(date -u +%Y%m%dT%H%M%SZ)"
fi

install -o root -g root -m 0644 "$SERVICE_SRC" "$SERVICE_DST"
install -o root -g root -m 0644 "$TIMER_SRC" "$TIMER_DST"
chmod 0755 "$APP_ROOT/scripts/run_historical_source_refresh_rclone.sh"

systemctl daemon-reload
systemctl enable --now kalman-shadow-bakeoff-daily.timer

echo "INSTALLED kalman-shadow-bakeoff-daily.timer"
systemctl list-timers kalman-shadow-bakeoff-daily.timer --all --no-pager
