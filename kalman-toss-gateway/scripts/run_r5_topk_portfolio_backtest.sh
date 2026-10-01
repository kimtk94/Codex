#!/usr/bin/env bash

REPO="${REPO:-$HOME/Codex}"
APP="$REPO/kalman-toss-gateway"
PYTHON="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

cd "$APP" || exit 1

"$PYTHON"   research/quant_stack/r5_topk_portfolio_backtest.py   "$@"

RC=$?

echo
echo "===== R5.1 TOP-K PORTFOLIO BACKTEST ====="
echo "exit_code=$RC"

exit "$RC"
