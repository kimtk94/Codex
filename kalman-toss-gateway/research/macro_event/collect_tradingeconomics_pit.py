from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill US macro calendar from Trading Economics PIT endpoints"
    )
    p.add_argument("--api-key", default=os.environ.get("TRADING_ECONOMICS_API_KEY"))
    p.add_argument("--spec", required=True)
    p.add_argument("--start-date", default="2017-01-01")
    p.add_argument("--end-date", default=pd.Timestamp.utcnow().date().isoformat())
    p.add_argument("--output", required=True)
    p.add_argument("--country", default="united states")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--sleep-seconds", type=float, default=0.15)
    return p.parse_args()


_MULTIPLIER = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_numeric(value: Any) -> float:
    if value is None:
        return math.nan
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return math.nan

    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "null", "n/a", "-"}:
        return math.nan

    # Strip currency/prefix text but retain sign, decimal, exponent and scale suffix.
    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([KMBT%]?)\s*$", text)
    if not m:
        return math.nan
    number = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix in _MULTIPLIER:
        number *= _MULTIPLIER[suffix]
    return number


def _request_json(url: str, *, timeout: float) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        if payload.get("status") in {401, 403}:
            raise RuntimeError(f"Trading Economics auth error: {payload}")
        payload = [payload]
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected Trading Economics payload: {type(payload).__name__}")
    return [dict(x) for x in payload]


def _indicator_rows(
    *,
    api_key: str,
    country: str,
    indicator: str,
    start_date: str,
    end_date: str,
    timeout: float,
) -> list[dict[str, Any]]:
    country_q = quote(country, safe="")
    indicator_q = quote(indicator, safe="")
    url = (
        "https://api.tradingeconomics.com/calendar/country/"
        f"{country_q}/indicator/{indicator_q}/{start_date}/{end_date}"
        f"?c={quote(api_key, safe='')}&f=json&values=true"
    )
    return _request_json(url, timeout=timeout)


def normalize_row(row: dict[str, Any], event_type: str, provider_indicator: str) -> dict[str, Any]:
    calendar_id = str(row.get("CalendarId") or "").strip()
    release = pd.to_datetime(row.get("Date"), utc=True, errors="coerce")
    if pd.isna(release):
        raise ValueError(f"unparseable Date for CalendarId={calendar_id}")

    actual_value = row.get("ActualValue")
    previous_value = row.get("PreviousValue")
    forecast_value = row.get("ForecastValue")
    if actual_value is None:
        actual_value = parse_numeric(row.get("Actual"))
    if previous_value is None:
        previous_value = parse_numeric(row.get("Previous"))
    if forecast_value is None:
        forecast_value = parse_numeric(row.get("Forecast"))

    # Trading Economics defines Revised as the previous release before revision,
    # while Previous is the revised previous release. Store both explicitly.
    revised_previous = previous_value
    previous_pre_revision = parse_numeric(row.get("Revised"))
    if math.isnan(previous_pre_revision):
        previous_pre_revision = previous_value

    return {
        "event_id": f"TE:{calendar_id}" if calendar_id else (
            f"TE:{event_type}:{release.isoformat()}:{row.get('Reference','')}"
        ),
        "event_type": event_type,
        "release_time": release,
        "available_time": release,
        "actual": float(actual_value) if actual_value is not None else math.nan,
        "consensus": float(forecast_value) if forecast_value is not None else math.nan,
        "previous": float(previous_pre_revision),
        "revised_previous": float(revised_previous) if revised_previous is not None else math.nan,
        "provider": "TRADING_ECONOMICS",
        "provider_indicator": provider_indicator,
        "provider_calendar_id": calendar_id,
        "country": row.get("Country"),
        "category_raw": row.get("Category"),
        "event_raw": row.get("Event"),
        "reference": row.get("Reference"),
        "reference_date": row.get("ReferenceDate"),
        "importance": row.get("Importance"),
        "source": row.get("Source"),
        "source_url": row.get("SourceURL"),
        "unit_raw": row.get("Unit"),
        "ticker": row.get("Ticker"),
        "symbol": row.get("Symbol"),
        "provider_last_update": row.get("LastUpdate"),
        "actual_raw": row.get("Actual"),
        "previous_raw": row.get("Previous"),
        "forecast_raw": row.get("Forecast"),
        "revised_raw": row.get("Revised"),
    }


def collect_pit_events(
    spec: dict[str, Any],
    *,
    api_key: str,
    country: str,
    start_date: str,
    end_date: str,
    timeout: float,
    sleep_seconds: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for event_type, definition in spec["event_definitions"].items():
        aliases = list(definition.get("tradingeconomics_indicators") or [])
        if not aliases:
            continue

        event_seen = False
        for indicator in aliases:
            try:
                payload = _indicator_rows(
                    api_key=api_key,
                    country=country,
                    indicator=str(indicator),
                    start_date=start_date,
                    end_date=end_date,
                    timeout=timeout,
                )
                normalized = [
                    normalize_row(r, str(event_type), str(indicator))
                    for r in payload
                    if str(r.get("Country") or "").strip().lower()
                    == country.strip().lower()
                ]
                if normalized:
                    rows.extend(normalized)
                    event_seen = True
                    break
            except Exception as exc:
                errors.append(f"{event_type}/{indicator}: {type(exc).__name__}: {exc}")
            time.sleep(max(0.0, sleep_seconds))

        if not event_seen:
            errors.append(f"{event_type}: no rows from configured aliases")

    if not rows:
        raise RuntimeError("Trading Economics PIT backfill returned no macro events")

    frame = pd.DataFrame(rows)
    frame = (
        frame.sort_values(["event_type", "available_time", "event_id"])
        .drop_duplicates("event_id", keep="last")
        .reset_index(drop=True)
    )
    frame.attrs["collection_errors"] = errors
    return frame


def main() -> int:
    args = parse_args()
    if not args.api_key:
        raise RuntimeError(
            "TRADING_ECONOMICS_API_KEY is required unless --api-key is supplied"
        )

    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    frame = collect_pit_events(
        spec,
        api_key=str(args.api_key),
        country=str(args.country),
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        timeout=float(args.timeout),
        sleep_seconds=float(args.sleep_seconds),
    )

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)

    status = {
        "status": "READY",
        "provider": "TRADING_ECONOMICS_POINT_IN_TIME",
        "rows": int(len(frame)),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "event_types": frame["event_type"].value_counts().sort_index().to_dict(),
        "consensus_coverage": float(frame["consensus"].notna().mean()),
        "min_available_time": frame["available_time"].min(),
        "max_available_time": frame["available_time"].max(),
        "collection_warnings": list(frame.attrs.get("collection_errors") or []),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    out.with_suffix(".status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
