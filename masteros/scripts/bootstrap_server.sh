#!/usr/bin/env bash

ROOT="${MASTEROS_ROOT:-/srv/masteros}"
REPO="${MASTEROS_REPO:-$ROOT/repo}"
VAULT="${MASTEROS_VAULT:-$ROOT/vault}"
CACHE="${MASTEROS_CACHE:-$ROOT/cache}"

mkdir -p "$ROOT" "$VAULT" "$CACHE"

printf 'MasterOS root: %s\n' "$ROOT"
printf 'Vault: %s\n' "$VAULT"

for cmd in python3 docker rclone git; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "OK: $cmd"
  else
    echo "WARN: $cmd is not installed"
  fi
done

if [ -f "$REPO/masteros/docker-compose.yml" ] && command -v docker >/dev/null 2>&1; then
  echo "Starting SilverBullet on localhost:3000"
  docker compose -f "$REPO/masteros/docker-compose.yml" up -d
fi

if [ -f "$REPO/masteros/scripts/sync_all.sh" ]; then
  bash "$REPO/masteros/scripts/sync_all.sh"
fi

echo "Bootstrap finished. Put HTTPS/reverse proxy in front of localhost:3000 before exposing it externally."
