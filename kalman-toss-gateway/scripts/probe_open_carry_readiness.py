#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--env-file",
        default=os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
    )
    p.add_argument(
        "--app-root",
        default=os.environ.get("KALMAN_APP_ROOT", "/opt/kalman/app"),
    )
    args = p.parse_args()

    env_file = Path(args.env_file)
    if env_file.exists():
        load_dotenv(env_file, override=True)

    app_root = Path(args.app_root)
    watcher = app_root / "scripts" / "run_execution_watch.sh"
    clock = app_root / "scripts" / "run_us_market_clock.sh"
    shadow = app_root / "engine" / "open_carry_shadow.py"
    live = app_root / "engine" / "open_carry_live.py"

    watcher_text = watcher.read_text(errors="ignore") if watcher.exists() else ""
    clock_text = clock.read_text(errors="ignore") if clock.exists() else ""
    shadow_text = shadow.read_text(errors="ignore") if shadow.exists() else ""

    schedule_ok = all(
        token in shadow_text
        for token in ("(9, 30)", "(9, 35)", "(9, 40)", "(9, 45)")
    )
    execution_window_ok = (
        "NY_HOUR == 9 && NY_MIN >= 25" in clock_text
        and "run_execution_watch.sh" in clock_text
    )
    shadow_wired = "engine.open_carry_shadow" in watcher_text
    live_wired = "engine.open_carry_live" in watcher_text

    payload = {
        "status": "READY" if schedule_ok and execution_window_ok and shadow_wired else "DEGRADED",
        "shadow": {
            "wired": shadow_wired,
            "schedule_et": ["09:30", "09:35", "09:40", "09:45"],
            "schedule_contract_ok": schedule_ok,
            "execution_window_starts_0925_et": execution_window_ok,
            "mirror_path": os.environ.get(
                "OPEN_CARRY_SHADOW_MIRROR_PATH",
                "/home/taehoon/kalman-data/trading/open-carry-shadow-latest.json",
            ),
            "broker_orders": False,
        },
        "live": {
            "wired": live_wired,
            "open_carry_live_enabled": _bool("OPEN_CARRY_LIVE_ENABLED"),
            "auto_trade_entry_enabled": _bool("AUTO_TRADE_ENTRY_ENABLED", "true"),
            "auto_trade_enabled": _bool("AUTO_TRADE_ENABLED"),
            "execution_mode": os.environ.get("AUTO_TRADE_EXECUTION_MODE"),
            "signal_policy": os.environ.get("AUTO_TRADE_SIGNAL_POLICY"),
            "strategy_version": os.environ.get("AUTO_TRADE_STRATEGY_VERSION"),
            "confirmation_present": bool(
                os.environ.get("OPEN_CARRY_LIVE_CONFIRM", "").strip()
            ),
            "order_krw": os.environ.get("OPEN_CARRY_ORDER_KRW"),
            "max_total_krw": os.environ.get("OPEN_CARRY_MAX_TOTAL_KRW"),
            "max_entries": os.environ.get("OPEN_CARRY_MAX_ENTRIES"),
        },
        "trade_execution": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
