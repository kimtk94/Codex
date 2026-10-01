#!/usr/bin/env bash

REPO="${REPO:-$HOME/Codex}"
APP="$REPO/kalman-toss-gateway"

choose_python() {
  if [ -n "${KALMAN_RESEARCH_PYTHON:-}" ] && [ -x "${KALMAN_RESEARCH_PYTHON}" ]; then
    "${KALMAN_RESEARCH_PYTHON}" -c 'import numpy, pandas, pyarrow' >/dev/null 2>&1
    if [ "$?" -eq 0 ]; then
      printf '%s\n' "${KALMAN_RESEARCH_PYTHON}"
      return 0
    fi
  fi

  for candidate in     "$HOME/.venv/bin/python"     "$HOME/venv/bin/python"     "$HOME/miniconda3/bin/python"     "$HOME/anaconda3/bin/python"     "$(command -v python3 2>/dev/null)"     "/opt/kalman/.venv/bin/python"
  do
    [ -n "$candidate" ] || continue
    [ -x "$candidate" ] || continue

    "$candidate" -c 'import numpy, pandas, pyarrow' >/dev/null 2>&1
    if [ "$?" -eq 0 ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

PYTHON="$(choose_python)"

if [ -z "$PYTHON" ]; then
  echo "[ERROR] No Python interpreter with numpy+pandas+pyarrow found."
  echo
  echo "Checked:"
  echo "  KALMAN_RESEARCH_PYTHON"
  echo "  $HOME/.venv/bin/python"
  echo "  $HOME/venv/bin/python"
  echo "  $HOME/miniconda3/bin/python"
  echo "  $HOME/anaconda3/bin/python"
  echo "  python3"
  echo "  /opt/kalman/.venv/bin/python"
  echo
  echo "Recommended research venv:"
  echo "  python3 -m venv $HOME/.venv-kalman-research"
  echo "  $HOME/.venv-kalman-research/bin/pip install -U pip"
  echo "  $HOME/.venv-kalman-research/bin/pip install numpy pandas pyarrow pytest"
  echo "  export KALMAN_RESEARCH_PYTHON=$HOME/.venv-kalman-research/bin/python"
  exit 2
fi

echo "[PYTHON] $PYTHON"
"$PYTHON" -c 'import sys, numpy, pandas, pyarrow; print("[PYTHON_VERSION]", sys.version.split()[0]); print("[NUMPY]", numpy.__version__); print("[PANDAS]", pandas.__version__); print("[PYARROW]", pyarrow.__version__)'

cd "$APP" || exit 1

"$PYTHON"   research/quant_stack/r5_topk_portfolio_backtest.py   "$@"

RC=$?

echo
echo "===== R5.1 TOP-K PORTFOLIO BACKTEST ====="
echo "exit_code=$RC"

exit "$RC"
