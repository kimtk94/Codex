#!/usr/bin/env bash

set +e
set +u
set +o pipefail 2>/dev/null || true

ROOT="/srv/is-analysis/IS_Analysis_V3"
REPO_DIR="$ROOT/.git_repos/Codex"
TARGET="$ROOT/research/multi_organ_aging"
BRANCH="research/multi-organ-aging-20260927"
URL="https://github.com/kimtk94/Codex.git"

mkdir -p "$ROOT/.git_repos" "$ROOT/research"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[CLONE] $URL -> $REPO_DIR"
  git clone --branch "$BRANCH" --single-branch "$URL" "$REPO_DIR"
  RC=$?
  if [ "$RC" -ne 0 ]; then
    echo "[ERROR] clone failed rc=$RC"
    exit "$RC"
  fi
else
  echo "[UPDATE] $REPO_DIR"
  git -C "$REPO_DIR" fetch origin "$BRANCH"
  RC1=$?
  git -C "$REPO_DIR" checkout "$BRANCH"
  RC2=$?
  git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
  RC3=$?
  if [ "$RC1" -ne 0 ] || [ "$RC2" -ne 0 ] || [ "$RC3" -ne 0 ]; then
    echo "[ERROR] git update failed fetch=$RC1 checkout=$RC2 pull=$RC3"
    exit 1
  fi
fi

SOURCE="$REPO_DIR/research/multi_organ_aging"

if [ -L "$TARGET" ]; then
  ln -sfn "$SOURCE" "$TARGET"
elif [ ! -e "$TARGET" ]; then
  ln -s "$SOURCE" "$TARGET"
else
  echo "[INFO] Existing project directory detected: $TARGET"
  echo "[INFO] Updating files in place without deleting local files."
  rsync -a "$SOURCE/" "$TARGET/"
fi

echo "===== CURRENT GIT ====="
git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD
git -C "$REPO_DIR" rev-parse HEAD

echo
echo "===== PROJECT ====="
echo "$TARGET"
echo "===== DONE ====="
