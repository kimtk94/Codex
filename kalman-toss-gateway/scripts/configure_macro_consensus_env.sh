#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
RUN="${APP_ROOT}/scripts/run_macro_event_features_v1.sh"
MODE="${1:-status}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $0 {enable|disable|status}" >&2
  exit 1
fi

[ -f "$ENV_FILE" ] || { echo "[FAIL] env missing: $ENV_FILE" >&2; exit 2; }
[ -x "$RUN" ] || { echo "[FAIL] macro runner missing: $RUN" >&2; exit 3; }

show_state() {
  echo "===== MACRO CONSENSUS ENV ====="
  python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
values = {}
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

enabled = values.get("KALMAN_MACRO_CONSENSUS_ENABLED", "").lower() in {"1", "true", "yes", "on"}
te = values.get("TRADING_ECONOMICS_API_KEY", "")
fred = values.get("FRED_API_KEY", "") or values.get("FRED_KEY", "")
print(f"KALMAN_MACRO_CONSENSUS_ENABLED={'true' if enabled else 'false'}")
print(f"TRADING_ECONOMICS_API_KEY={'SET' if te else 'MISSING'}")
print(f"FRED_API_KEY={'SET' if fred else 'MISSING'}")
PY
}

write_env() {
  local enabled="$1"
  local te_key="${2:-}"
  local stamp backup
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="${ENV_FILE}.bak.${stamp}"
  cp -a "$ENV_FILE" "$backup"
  chmod 0600 "$backup"

  CFG_ENABLED="$enabled" CFG_TE_KEY="$te_key" python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
enabled = os.environ["CFG_ENABLED"]
te_key = os.environ.get("CFG_TE_KEY", "")
updates = {"KALMAN_MACRO_CONSENSUS_ENABLED": enabled}
if te_key:
    updates["TRADING_ECONOMICS_API_KEY"] = te_key

lines = path.read_text(encoding="utf-8").splitlines()
out = []
seen = set()
for raw in lines:
    if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
        out.append(raw)
        continue
    key = raw.split("=", 1)[0].strip()
    if key in updates:
        if key not in seen:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        continue
    out.append(raw)

missing = [k for k in updates if k not in seen]
if missing:
    if out and out[-1] != "":
        out.append("")
    out.append("# --- Managed macro consensus settings ---")
    for key in missing:
        out.append(f"{key}={updates[key]}")

tmp = path.with_name(path.name + ".tmp")
tmp.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
path.chmod(0o600)
PY
  echo "[INFO] backup=$backup"
}

case "$MODE" in
  status)
    show_state
    echo
    KALMAN_ENV_FILE="$ENV_FILE" "$RUN" status
    ;;
  enable)
    te_key="${TRADING_ECONOMICS_API_KEY:-}"
    if [ -z "$te_key" ]; then
      if [ -t 0 ]; then
        read -r -s -p "Trading Economics API key: " te_key
        echo
      else
        echo "[FAIL] TRADING_ECONOMICS_API_KEY is missing and no interactive terminal is available." >&2
        exit 4
      fi
    fi
    if [ -z "$te_key" ]; then
      echo "[FAIL] Empty Trading Economics API key." >&2
      exit 5
    fi
    case "${te_key,,}" in
      guest|guest:guest)
        echo "[FAIL] Demo guest credentials are intentionally rejected for Kalman consensus ingestion." >&2
        exit 6
        ;;
    esac

    write_env true "$te_key"
    unset te_key
    echo "[PASS] Macro consensus provider enabled. Trading gates were not modified."
    show_state
    echo
    echo "===== ONE BUILD ====="
    KALMAN_ENV_FILE="$ENV_FILE" "$RUN" build
    echo
    echo "===== STATUS ====="
    KALMAN_ENV_FILE="$ENV_FILE" "$RUN" status
    ;;
  disable)
    write_env false ""
    echo "[PASS] Macro consensus provider disabled. Existing API key was preserved."
    show_state
    ;;
  *)
    echo "Usage: sudo $0 {enable|disable|status}" >&2
    exit 64
    ;;
esac
