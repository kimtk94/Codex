#!/usr/bin/env bash

ROOT="${MASTEROS_ROOT:-/srv/masteros}"
VAULT="${MASTEROS_VAULT:-$ROOT/vault}"
CACHE="${MASTEROS_CACHE:-$ROOT/cache}"
REPO="${MASTEROS_REPO:-$ROOT/repo}"
CSS_DB="${CSS_DB:-$CACHE/css_project_manager.sqlite3}"
RESEARCH_ROOT="${RESEARCH_ROOT:-/srv/is-analysis}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
CSS_DRIVE_DB="${CSS_DRIVE_DB:-Novogene_CSS/state/css_project_manager.sqlite3}"
VAULT_DRIVE_PATH="${VAULT_DRIVE_PATH:-MasterOS_Vault}"
CSS_SHEET_ID="${CSS_SHEET_ID:-}"
CSS_SHEET_SNAPSHOT="${CSS_SHEET_SNAPSHOT:-$CACHE/css_sheet_snapshot.json}"
GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-}"

mkdir -p "$VAULT" "$CACHE"

if [ -n "$RCLONE_REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  echo "[1/5] Refresh CSS DB from Google Drive"
  rclone copyto "$RCLONE_REMOTE:$CSS_DRIVE_DB" "$CSS_DB" --drive-skip-gdocs
else
  echo "[1/5] Skip Drive pull: configure RCLONE_REMOTE to enable it"
fi

if [ -n "$CSS_SHEET_ID" ] && [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
  echo "[2/6] Refresh canonical CSS Google Sheet snapshot"
  python3 "$REPO/masteros/scripts/fetch_css_sheet_snapshot.py" \
    --sheet-id "$CSS_SHEET_ID" \
    --credentials "$GOOGLE_APPLICATION_CREDENTIALS" \
    --output "$CSS_SHEET_SNAPSHOT"
else
  echo "[2/6] Skip canonical Sheet snapshot: configure CSS_SHEET_ID and GOOGLE_APPLICATION_CREDENTIALS"
fi

if [ -f "$CSS_DB" ]; then
  echo "[3/6] Generate CSS knowledge graph"
  CSS_ARGS=(--db "$CSS_DB" --vault "$VAULT")
  if [ -f "$CSS_SHEET_SNAPSHOT" ]; then
    CSS_ARGS+=(--sheet-snapshot "$CSS_SHEET_SNAPSHOT")
  fi
  python3 "$REPO/masteros/scripts/css_to_vault.py" "${CSS_ARGS[@]}"
else
  echo "[3/6] Skip CSS: DB missing at $CSS_DB"
fi

if [ -d "$RESEARCH_ROOT" ]; then
  echo "[4/6] Generate research snapshots"
  python3 "$REPO/masteros/scripts/research_to_vault.py" --root "$RESEARCH_ROOT" --vault "$VAULT"
else
  echo "[4/6] Skip research: root missing at $RESEARCH_ROOT"
fi

if [ -n "$RCLONE_REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  echo "[5/6] Mirror generated Vault to Google Drive"
  rclone sync "$VAULT" "$RCLONE_REMOTE:$VAULT_DRIVE_PATH" \
    --exclude ".obsidian/workspace*" \
    --exclude ".trash/**"
else
  echo "[5/6] Skip Drive push"
fi

if git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[6/6] Commit Vault snapshot if changed"
  git -C "$VAULT" add -A
  git -C "$VAULT" diff --cached --quiet || git -C "$VAULT" commit -m "chore: refresh MasterOS vault"
else
  echo "[6/6] Vault is not a Git worktree; skip commit"
fi
