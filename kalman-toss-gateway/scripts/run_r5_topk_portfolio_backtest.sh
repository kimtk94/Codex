#!/usr/bin/env bash

REPO="${REPO:-$HOME/Codex}"
APP="$REPO/kalman-toss-gateway"
PYTHON="${PYTHON:-$(command -v python3)}"

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
  echo "[ERROR] python3 not found"
  exit 2
fi

echo "[PYTHON] $PYTHON"
"$PYTHON" -c 'import sys; print("[PYTHON_VERSION]", sys.version.split()[0])'

"$PYTHON" -c 'import numpy, pandas, pyarrow' >/dev/null 2>&1
DEPS_RC=$?

if [ "$DEPS_RC" -ne 0 ]; then
  echo "[INFO] Installing research dependencies to user site-packages"
  "$PYTHON" -m pip install --user --break-system-packages --upgrade numpy pandas pyarrow pytest
  PIP_RC=$?
  if [ "$PIP_RC" -ne 0 ]; then
    echo "[ERROR] pip install failed: rc=$PIP_RC"
    exit "$PIP_RC"
  fi
fi

"$PYTHON" -c 'import numpy, pandas, pyarrow; print("[NUMPY]", numpy.__version__); print("[PANDAS]", pandas.__version__); print("[PYARROW]", pyarrow.__version__)'
VERIFY_RC=$?

if [ "$VERIFY_RC" -ne 0 ]; then
  echo "[ERROR] numpy/pandas/pyarrow import verification failed"
  exit "$VERIFY_RC"
fi

cd "$APP" || exit 1

"$PYTHON"   research/quant_stack/r5_topk_portfolio_backtest.py   "$@"

RC=$?

echo
echo "===== R5.1 TOP-K PORTFOLIO BACKTEST ====="
echo "exit_code=$RC"

exit "$RC"
