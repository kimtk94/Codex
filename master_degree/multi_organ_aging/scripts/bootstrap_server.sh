#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ROOT="/srv/is-analysis"
REPO="$ROOT/IS_Analysis_V3"
REMOTE_REPO="${MOA_GIT_REMOTE:-https://github.com/kimtk94/Codex.git}"
BRANCH="${MOA_GIT_BRANCH:-research/multi-organ-aging-20260927}"

echo "===== MULTI-ORGAN AGING SERVER BOOTSTRAP ====="
echo "repo=$REPO"
echo "branch=$BRANCH"

if [ ! -d "$REPO/.git" ]; then
  mkdir -p "$ROOT"
  git clone "$REMOTE_REPO" "$REPO"
  RC_CLONE=$?
  echo "clone rc=$RC_CLONE"
fi

cd "$REPO" || exit 1

git fetch origin "$BRANCH"
RC_FETCH=$?
echo "fetch rc=$RC_FETCH"

git checkout "$BRANCH"
RC_CHECKOUT=$?
if [ "$RC_CHECKOUT" -ne 0 ]; then
  git checkout -b "$BRANCH" "origin/$BRANCH"
  RC_CHECKOUT=$?
fi
echo "checkout rc=$RC_CHECKOUT"

git pull --ff-only origin "$BRANCH"
RC_PULL=$?
echo "pull rc=$RC_PULL"

BASE="$REPO/master_degree/multi_organ_aging"

python3 -m pip install -r "$BASE/requirements.txt"
RC_PIP=$?
echo "pip rc=$RC_PIP"

python3 -m compileall "$BASE/src"
RC_COMPILE=$?
echo "compile rc=$RC_COMPILE"

python3 -m pytest -q "$BASE/tests"
RC_TEST=$?
echo "pytest rc=$RC_TEST"

printf "FINAL fetch=%s checkout=%s pull=%s pip=%s compile=%s test=%s\n"   "$RC_FETCH" "$RC_CHECKOUT" "$RC_PULL" "$RC_PIP" "$RC_COMPILE" "$RC_TEST"

exit 0
