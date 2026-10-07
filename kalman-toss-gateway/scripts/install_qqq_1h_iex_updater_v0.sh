#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_ROOT="/opt/kalman/qqq-updater-v0"
SERVICE_SRC="$APP_ROOT/config/kalman-qqq-1h-iex-updater-v0.service"
TIMER_SRC="$APP_ROOT/config/kalman-qqq-1h-iex-updater-v0.timer"
MODULE_SRC="$APP_ROOT/research/quant_stack/qqq_1h_iex_updater_v0.py"
RUNNER_SRC="$APP_ROOT/scripts/run_qqq_1h_iex_updater_v0.sh"
SERVICE_DST="/etc/systemd/system/kalman-qqq-1h-iex-updater-v0.service"
TIMER_DST="/etc/systemd/system/kalman-qqq-1h-iex-updater-v0.timer"

for required in "$SERVICE_SRC" "$TIMER_SRC" "$MODULE_SRC" "$RUNNER_SRC"; do
  if [ ! -f "$required" ]; then
    echo "[FAIL] missing source: $required" >&2
    exit 10
  fi
done

echo "[1/7] deploy root-owned updater snapshot"
sudo mkdir -p "$DEPLOY_ROOT/research/quant_stack" "$DEPLOY_ROOT/scripts"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi

sudo cp "$MODULE_SRC" "$DEPLOY_ROOT/research/quant_stack/qqq_1h_iex_updater_v0.py"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo cp "$RUNNER_SRC" "$DEPLOY_ROOT/scripts/run_qqq_1h_iex_updater_v0.sh"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo chown -R root:root "$DEPLOY_ROOT"
sudo chmod 0755 "$DEPLOY_ROOT" "$DEPLOY_ROOT/scripts"
sudo chmod 0644 "$DEPLOY_ROOT/research/quant_stack/qqq_1h_iex_updater_v0.py"
sudo chmod 0755 "$DEPLOY_ROOT/scripts/run_qqq_1h_iex_updater_v0.sh"

if [ ! -f /home/taehoon/.config/rclone/rclone.conf ]; then
  echo "[FAIL] user rclone config missing" >&2
  exit 11
fi
sudo cp /home/taehoon/.config/rclone/rclone.conf "$DEPLOY_ROOT/rclone.conf"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo chown root:root "$DEPLOY_ROOT/rclone.conf"
sudo chmod 0600 "$DEPLOY_ROOT/rclone.conf"

echo "[2/7] create isolated root-owned venv"
if [ ! -x "$DEPLOY_ROOT/.venv/bin/python" ]; then
  sudo /usr/bin/python3 -m venv "$DEPLOY_ROOT/.venv"
  RC="$?"
  if [ "$RC" -ne 0 ]; then exit "$RC"; fi
fi
sudo "$DEPLOY_ROOT/.venv/bin/python" -m pip install --disable-pip-version-check \
  "numpy==2.5.3" "pandas==3.0.6" "pyarrow==25.0.1"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo chown -R root:root "$DEPLOY_ROOT/.venv"

echo "[3/7] install systemd units"
sudo cp "$SERVICE_SRC" "$SERVICE_DST"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo cp "$TIMER_SRC" "$TIMER_DST"
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi
sudo chown root:root "$SERVICE_DST" "$TIMER_DST"
sudo chmod 0644 "$SERVICE_DST" "$TIMER_DST"

echo "[4/7] reload systemd"
sudo systemctl daemon-reload
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi

echo "[5/7] one-shot source/overlap validation"
sudo systemctl start kalman-qqq-1h-iex-updater-v0.service
RC="$?"
if [ "$RC" -ne 0 ]; then
  echo "[FAIL] one-shot validation failed; timer NOT enabled." >&2
  sudo systemctl status kalman-qqq-1h-iex-updater-v0.service --no-pager || true
  sudo journalctl -u kalman-qqq-1h-iex-updater-v0.service -n 80 --no-pager || true
  exit "$RC"
fi

echo "[6/7] enable hourly timer only after successful validation"
sudo systemctl enable --now kalman-qqq-1h-iex-updater-v0.timer
RC="$?"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi

echo "[7/7] final status"
sudo systemctl status kalman-qqq-1h-iex-updater-v0.timer --no-pager || true
sudo systemctl status kalman-qqq-1h-iex-updater-v0.service --no-pager || true
echo "[READY] QQQ 1h IEX updater installed; live trading service was not modified."
