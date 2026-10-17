#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_QQQ_UPDATER_PYTHON:-$APP_ROOT/.venv/bin/python}"
CANONICAL="${KALMAN_QQQ_1H_CANONICAL:-/home/taehoon/kalman-data/market/1h/QQQ_1h_2017plus.parquet}"
STATUS="${KALMAN_QQQ_1H_STATUS:-/home/taehoon/kalman-data/market/1h/qqq_1h_iex_updater_v0.json}"
DRIVE_REMOTE="${KALMAN_QQQ_1H_DRIVE_REMOTE:-gdrive:US_ETF/history_1h/QQQ_1h_2017plus.parquet}"
RCLONE_CONFIG="${KALMAN_RCLONE_CONFIG:-/home/taehoon/.config/rclone/rclone.conf}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] updater python missing: $PY" >&2
  exit 10
fi

"$PY" "$APP_ROOT/research/quant_stack/qqq_1h_iex_updater_v0.py" \
  --symbol QQQ \
  --canonical "$CANONICAL" \
  --overlap-days 5 \
  --adjustment raw \
  --drive-remote "$DRIVE_REMOTE" \
  --rclone-config "$RCLONE_CONFIG" \
  --status "$STATUS" \
  "$@"

exit "$?"
