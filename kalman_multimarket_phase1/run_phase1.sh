#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kalman}"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"
LOG_DIR="${LOG_DIR:-$APP_DIR/logs}"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

exec "$PYTHON" multimarket_phase1.py
