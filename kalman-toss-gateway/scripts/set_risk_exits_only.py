from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


UPDATES = {
    "AUTO_TRADE_ENABLED": "true",
    "AUTO_TRADE_ENTRY_ENABLED": "false",
    "AUTO_TRADE_EXECUTION_MODE": "LIVE",
    "TRADING_ENABLED": "true",
    "LIVE_TRADING_CONFIRM": "CONFIRM_LIVE_TRADING",
    "OPEN_CARRY_LIVE_ENABLED": "false",
}


def rewrite_env(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(path.name + f".risk-exits-only-{stamp}.bak")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)

    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in UPDATES:
            if key not in seen:
                out.append(f"{key}={UPDATES[key]}")
                seen.add(key)
            continue
        out.append(line)

    missing = [key for key in UPDATES if key not in seen]
    if missing:
        if out and out[-1] != "":
            out.append("")
        out.append("# --- Cost gate: risk exits only ---")
        out.extend(f"{key}={UPDATES[key]}" for key in missing)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return backup


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", type=Path, default=Path("/opt/kalman/.env"))
    args = p.parse_args()
    backup = rewrite_env(args.env_file)
    print(f"RISK_EXITS_ONLY_ENV_APPLIED={args.env_file}")
    print(f"BACKUP={backup}")
    for key, value in UPDATES.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
