#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 3
APP_ROOT="${KALMAN_APP_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PY="${KALMAN_PM_PYTHON:-/home/taehoon/.venvs/kalman-pm-research/bin/python}"
SPEC="${KALMAN_PM_OOS_SPEC:-$APP_ROOT/config/prediction-market-oos-v0.json}"
CONFIG="${KALMAN_PM_CONFIG:-$APP_ROOT/config/prediction-market-layer-v0.json}"
DATA_ROOT="${KALMAN_PM_DATA_ROOT:-/home/taehoon/kalman-data/prediction-market}"
QQQ_LOCAL="${KALMAN_PM_QQQ_LOCAL:-/home/taehoon/kalman-data/market/1h/QQQ_1h_2017plus.parquet}"
QQQ_DRIVE="${KALMAN_PM_QQQ_DRIVE:-gdrive:US_ETF/history_1h/QQQ_1h_2017plus.parquet}"
RCLONE_CONFIG="${KALMAN_PM_RCLONE_CONFIG:-/home/taehoon/.config/rclone/rclone.conf}"
STATUS="${KALMAN_PM_WATCH_STATUS:-$DATA_ROOT/oos-watch-v0/latest.json}"
LOCK="${KALMAN_PM_WATCH_LOCK:-$DATA_ROOT/oos-watch-v0/watch.lock}"

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x "$PY" ]; then
  echo "[FAIL] prediction-market research python missing: $PY" >&2
  exit 10
fi

"$PY" -m research.quant_stack.prediction_market_oos_watch_v0 \
  --app-root "$APP_ROOT" \
  --spec "$SPEC" \
  --config "$CONFIG" \
  --data-root "$DATA_ROOT" \
  --qqq-local "$QQQ_LOCAL" \
  --qqq-drive "$QQQ_DRIVE" \
  --rclone-config "$RCLONE_CONFIG" \
  --status "$STATUS" \
  --lock "$LOCK" \
  "$@"

exit "$?"
