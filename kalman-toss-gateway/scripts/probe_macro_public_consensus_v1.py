#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from engine import macro_consensus_provider_v1 as consensus


UTC = timezone.utc


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    if path.exists():
        load_dotenv(path, override=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only public macro consensus calendar probe."
    )
    parser.add_argument(
        "--config",
        default="config/macro-event-features-v1.json",
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
    )
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    cfg = json.loads(Path(args.config).read_text())
    provider = cfg.get("trading_economics") or {}
    public = provider.get("public_calendar_fallback") or {}
    url = str(
        public.get("url")
        or "https://tradingeconomics.com/united-states/calendar"
    )

    with httpx.Client(
        timeout=float(public.get("timeout_seconds", 20)),
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 KalmanResearch/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        raw_rows = consensus.parse_public_calendar_html(response.text)

    us_spec = None
    for spec in consensus._provider_market_specs(cfg):
        if str(spec.get("market") or "").upper() == "US":
            us_spec = spec
            break
    if us_spec is None:
        raise SystemExit("US macro market config missing")

    now = datetime.now(UTC)
    targets = []
    for row in raw_rows:
        indicator = consensus.event_indicator_key(row, cfg, us_spec)
        if not indicator:
            continue
        release_at = consensus.parse_dt(row.get("Date"))
        if release_at is None:
            continue
        targets.append(
            {
                "indicator_key": indicator,
                "event_name": row.get("Event"),
                "calendar_id": row.get("CalendarId"),
                "release_at": release_at.isoformat(),
                "phase": "FUTURE" if release_at > now else "PAST",
                "actual": row.get("Actual"),
                "consensus": row.get("Forecast"),
                "te_forecast": row.get("TEForecast"),
                "consensus_available": bool(str(row.get("Forecast") or "").strip()),
            }
        )
    targets.sort(key=lambda row: row["release_at"])
    future = [row for row in targets if row["phase"] == "FUTURE"]

    runtime_default = bool(provider.get("runtime_enabled_default", False))
    runtime_enabled = consensus.env_bool(
        "KALMAN_MACRO_CONSENSUS_ENABLED",
        runtime_default,
    )
    status = "READY" if raw_rows and targets else "NO_TARGET_ROWS"
    if status == "READY" and not runtime_enabled:
        status = "RUNTIME_DISABLED"

    result = {
        "status": status,
        "checked_at": now.isoformat(),
        "provider": "trading_economics_public_calendar",
        "quality": str(
            public.get("quality")
            or "PUBLIC_WEB_CALENDAR_POINT_IN_TIME_SHADOW"
        ),
        "runtime_consensus_enabled": runtime_enabled,
        "authenticated_api_key_configured": bool(
            (os.environ.get("TRADING_ECONOMICS_API_KEY") or "").strip()
        ),
        "public_rows": len(raw_rows),
        "mapped_target_rows": len(targets),
        "future_target_rows": len(future),
        "future_with_consensus": sum(
            bool(row["consensus_available"]) for row in future
        ),
        "next_targets": future[:20],
        "trade_execution": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
