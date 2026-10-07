from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx


UTC = timezone.utc
TE_BASE_URL = "https://api.tradingeconomics.com"


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _sanitize_error(exc: Exception, credential: str) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if credential:
        message = message.replace(credential, "***")
        message = message.replace(quote(credential, safe=""), "***")
    return message


def parse_te_intraday_rows(
    payload: Any,
    *,
    expected_symbol: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("Trading Economics intraday response is not a list")

    rows: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("Symbol") or "").strip()
        if symbol.upper() != expected_symbol.upper():
            continue
        ts = _parse_dt(raw.get("Date"))
        close = raw.get("Close")
        if ts is None or close is None:
            continue
        try:
            close_value = float(close)
        except (TypeError, ValueError):
            continue
        if not (0.0 < close_value < 30.0):
            continue
        rows.append(
            {
                "ts": ts,
                "close_pct": close_value,
                "open_pct": _float_or_none(raw.get("Open")),
                "high_pct": _float_or_none(raw.get("High")),
                "low_pct": _float_or_none(raw.get("Low")),
            }
        )

    rows.sort(key=lambda row: row["ts"])
    dedup: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        dedup[row["ts"]] = row
    return [dedup[key] for key in sorted(dedup)]


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_intraday_reaction(
    rows: list[dict[str, Any]],
    *,
    event_at: datetime,
    horizons_minutes: list[int],
    baseline_max_gap_minutes: float,
    post_max_gap_minutes: float,
) -> dict[str, Any]:
    event_at = _parse_dt(event_at)
    if event_at is None:
        return {"status": "NO_EVENT_ANCHOR"}

    before = [row for row in rows if row["ts"] < event_at]
    if not before:
        return {"status": "BASELINE_UNAVAILABLE"}

    baseline = before[-1]
    baseline_gap = (event_at - baseline["ts"]).total_seconds() / 60.0
    if baseline_gap < 0 or baseline_gap > float(baseline_max_gap_minutes):
        return {
            "status": "BASELINE_GAP_EXCEEDED",
            "baseline_ts": baseline["ts"].isoformat(),
            "baseline_gap_minutes": baseline_gap,
        }

    horizons: dict[str, Any] = {}
    ready_count = 0
    for minutes in sorted({int(x) for x in horizons_minutes if int(x) > 0}):
        target = event_at + timedelta(minutes=minutes)
        candidates = [row for row in rows if row["ts"] >= target]
        key = f"{minutes}m"
        if not candidates:
            horizons[key] = {
                "status": "WAITING_HORIZON",
                "target_ts": target.isoformat(),
                "reaction_bps": None,
            }
            continue

        post = candidates[0]
        post_gap = (post["ts"] - target).total_seconds() / 60.0
        if post_gap > float(post_max_gap_minutes):
            horizons[key] = {
                "status": "POST_GAP_EXCEEDED",
                "target_ts": target.isoformat(),
                "post_ts": post["ts"].isoformat(),
                "post_gap_minutes": post_gap,
                "reaction_bps": None,
            }
            continue

        reaction_bps = (float(post["close_pct"]) - float(baseline["close_pct"])) * 100.0
        horizons[key] = {
            "status": "READY",
            "target_ts": target.isoformat(),
            "post_ts": post["ts"].isoformat(),
            "post_gap_minutes": post_gap,
            "yield_pct": float(post["close_pct"]),
            "reaction_bps": reaction_bps,
        }
        ready_count += 1

    return {
        "status": "READY" if ready_count else "WAITING_POST_EVENT_BARS",
        "event_at": event_at.isoformat(),
        "baseline_ts": baseline["ts"].isoformat(),
        "baseline_gap_minutes": baseline_gap,
        "baseline_yield_pct": float(baseline["close_pct"]),
        "horizons": horizons,
        "ready_horizons": ready_count,
    }


def fetch_intraday_us2y_reaction(
    config: dict[str, Any],
    *,
    event_at: datetime | None,
    as_of: datetime,
) -> dict[str, Any]:
    spec = config.get("intraday_us2y") or {}
    if not spec.get("enabled", False):
        return {
            "status": "DISABLED",
            "quality": "INTRADAY_NOT_USED",
            "trade_execution": False,
        }
    if event_at is None:
        return {
            "status": "NO_EVENT_ANCHOR",
            "quality": str(spec.get("quality") or "DELAYED_INTRADAY_RESEARCH"),
            "trade_execution": False,
        }

    event = _parse_dt(event_at)
    now = _parse_dt(as_of)
    assert event is not None and now is not None
    age_minutes = (now - event).total_seconds() / 60.0
    if age_minutes < float(spec.get("min_event_age_minutes", 0)):
        return {
            "status": "WAITING_MIN_EVENT_AGE",
            "event_age_minutes": age_minutes,
            "trade_execution": False,
        }
    if age_minutes > float(spec.get("max_event_age_minutes", 120)):
        return {
            "status": "OUTSIDE_COLLECTION_WINDOW",
            "event_age_minutes": age_minutes,
            "trade_execution": False,
        }

    credential = (os.environ.get("TRADING_ECONOMICS_API_KEY") or "").strip()
    if not credential:
        return {
            "status": "UNCONFIGURED_CREDENTIAL",
            "provider": "trading_economics",
            "trade_execution": False,
        }
    if credential.lower() in {"guest", "guest:guest"}:
        return {
            "status": "DEMO_CREDENTIALS_REJECTED",
            "provider": "trading_economics",
            "trade_execution": False,
        }

    symbol = str(spec.get("symbol") or "USGG2YR:IND")
    interval = str(spec.get("interval") or "1m")
    pre_minutes = int(spec.get("pre_event_minutes", 10))
    horizons = [int(x) for x in spec.get("horizons_minutes", [5, 15, 30, 60])]
    post_minutes = max(horizons or [60]) + int(spec.get("post_buffer_minutes", 5))

    start = event - timedelta(minutes=pre_minutes)
    end = min(now, event + timedelta(minutes=post_minutes))
    base_url = str(spec.get("base_url") or TE_BASE_URL).rstrip("/")
    url = f"{base_url}/markets/intraday/{quote(symbol, safe=':')}"
    params = {
        "c": credential,
        "agr": interval,
        "d1": start.strftime("%Y-%m-%d %H:%M"),
        "d2": end.strftime("%Y-%m-%d %H:%M"),
        "f": "json",
    }

    try:
        with httpx.Client(timeout=float(spec.get("timeout_seconds", 20))) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        rows = parse_te_intraday_rows(payload, expected_symbol=symbol)
        reaction = compute_intraday_reaction(
            rows,
            event_at=event,
            horizons_minutes=horizons,
            baseline_max_gap_minutes=float(spec.get("baseline_max_gap_minutes", 5)),
            post_max_gap_minutes=float(spec.get("post_max_gap_minutes", 2)),
        )
        return {
            **reaction,
            "provider": "trading_economics",
            "symbol": symbol,
            "interval": interval,
            "quality": str(spec.get("quality") or "DELAYED_INTRADAY_RESEARCH"),
            "rows": len(rows),
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "trade_execution": False,
        }
    except httpx.HTTPStatusError as exc:
        code = int(exc.response.status_code)
        return {
            "status": (
                "UNAVAILABLE_PROVIDER_ENTITLEMENT"
                if code in {401, 402, 403, 404, 410}
                else "PROVIDER_HTTP_ERROR"
            ),
            "provider": "trading_economics",
            "symbol": symbol,
            "http_status": code,
            "error": _sanitize_error(exc, credential),
            "trade_execution": False,
        }
    except Exception as exc:
        return {
            "status": "PROVIDER_ERROR",
            "provider": "trading_economics",
            "symbol": symbol,
            "error": _sanitize_error(exc, credential),
            "trade_execution": False,
        }


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    if path.exists():
        load_dotenv(path, override=False)


def probe_entitlement(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    as_of = _parse_dt(now or datetime.now(UTC))
    assert as_of is not None
    event_at = as_of - timedelta(minutes=15)
    return fetch_intraday_us2y_reaction(
        config,
        event_at=event_at,
        as_of=as_of,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Trading Economics US2Y intraday entitlement probe."
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

    _load_env_file(Path(args.env_file))
    config = json.loads(Path(args.config).read_text())
    result = probe_entitlement(config)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    bad = {
        "UNCONFIGURED_CREDENTIAL",
        "DEMO_CREDENTIALS_REJECTED",
        "UNAVAILABLE_PROVIDER_ENTITLEMENT",
        "PROVIDER_HTTP_ERROR",
        "PROVIDER_ERROR",
    }
    return 2 if result.get("status") in bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
