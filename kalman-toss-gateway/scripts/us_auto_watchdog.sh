#!/usr/bin/env python3
"""Read-only US market watchdog. Never submits orders or changes services."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

HEALTH_URL = "http://127.0.0.1:8787/health"
LOG_DIR = Path("/opt/kalman/logs")
CHECKS = (
    ("US_CYCLE", "us-cycle.log", "US_CYCLE_START_UTC", "US_CYCLE_DONE_UTC", 90, 20),
    ("EXECUTION_WATCH", "execution-watch.log", "EXECUTION_WATCH_START_UTC", "EXECUTION_WATCH_DONE_UTC", 20, 10),
)
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T[^\s]+)$")


def tail_text(path: Path, byte_count: int = 4 * 1024 * 1024) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - byte_count))
        return handle.read().decode("utf-8", errors="replace")


def latest_timestamp(text: str, marker: str) -> datetime | None:
    matches = re.findall(r"(?m)^" + re.escape(marker) + r"=([^\s]+)", text)
    for value in reversed(matches):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def main() -> int:
    now = datetime.now(timezone.utc)
    failures = []
    try:
        with urlopen(HEALTH_URL, timeout=5) as response:
            body = json.load(response)
            if response.status != 200 or body.get("status") != "ok":
                raise ValueError("Gateway health is not ok")
        print("WATCHDOG_PASS gateway_health")
    except Exception as exc:
        failures.append(f"gateway_health: {type(exc).__name__}: {exc}")

    for name, filename, start_marker, done_marker, max_age, stalled_after in CHECKS:
        try:
            text = tail_text(LOG_DIR / filename)
            done = latest_timestamp(text, done_marker)
            start = latest_timestamp(text, start_marker)
            if done is None:
                raise ValueError(f"missing {done_marker}")
            age = (now - done).total_seconds() / 60
            if age < -2 or age > max_age:
                raise ValueError(f"last completion age {age:.1f}m outside [0,{max_age}]m")
            if start is not None and start > done:
                elapsed = (now - start).total_seconds() / 60
                if elapsed > stalled_after:
                    raise ValueError(f"unfinished run age {elapsed:.1f}m")
            print(f"WATCHDOG_PASS {name} last_done={done.isoformat()} age_min={age:.1f}")
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    if failures:
        for reason in failures:
            print("WATCHDOG_FAIL " + reason, file=sys.stderr)
        return 1
    print("WATCHDOG_PASS all read-only checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
