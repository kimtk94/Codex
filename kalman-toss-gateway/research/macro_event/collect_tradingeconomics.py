from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests


TE_BASE = "https://api.tradingeconomics.com"

EVENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("CORE_CPI_MOM", re.compile(r"\b(core (inflation rate|cpi).*(mom|month)|core cpi mom)\b", re.I)),
    ("CPI_MOM", re.compile(r"\b(inflation rate mom|cpi.*(mom|month))\b", re.I)),
    ("CORE_PCE_MOM", re.compile(r"\bcore pce.*(mom|month)\b", re.I)),
    ("PCE_MOM", re.compile(r"\bpce (price )?index.*(mom|month)\b", re.I)),
    ("PPI_MOM", re.compile(r"\b(producer prices?.*(mom|month)|producer price.*(mom|month)|ppi.*(mom|month))\b", re.I)),
    ("AHE_MOM", re.compile(r"\baverage hourly earnings.*(mom|month)\b", re.I)),
    ("NFP", re.compile(r"\b(non[- ]?farm payrolls?|nonfarm payrolls?)\b", re.I)),
    ("UNEMPLOYMENT_RATE", re.compile(r"^unemployment rate$", re.I)),
    ("JOLTS_OPENINGS", re.compile(r"\b(jolts?.*job openings?|job openings jolts?)\b", re.I)),
    ("INITIAL_CLAIMS", re.compile(r"^initial jobless claims$", re.I)),
    ("RETAIL_SALES_MOM", re.compile(r"^retail sales mom$", re.I)),
    ("ISM_MANUFACTURING", re.compile(r"^ism manufacturing pmi$", re.I)),
    ("ISM_SERVICES", re.compile(r"^(ism (services|non[- ]manufacturing) pmi|non manufacturing pmi)$", re.I)),
    ("FOMC_DECISION", re.compile(r"\b(fed interest rate decision|fomc.*rate decision|interest rate)\b", re.I)),
]


def parse_args() -> argparse.Namespace:
    app_root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(
        description="Collect and normalize US Trading Economics point-in-time macro calendar events"
    )
    p.add_argument("--start", default="2017-01-01")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--output", required=True)
    p.add_argument("--country", default="united states")
    p.add_argument("--spec", default=str(app_root / "config/macro-event-v1-spec.json"))
    p.add_argument(
        "--api-key-env",
        default="TRADINGECONOMICS_API_KEY",
        help="environment variable containing the Trading Economics API key",
    )
    p.add_argument("--chunk-days", type=int, default=366)
    p.add_argument("--timeout-seconds", type=float, default=60.0)
    p.add_argument("--max-retries", type=int, default=4)
    p.add_argument("--sleep-seconds", type=float, default=0.10)
    p.add_argument(
        "--allow-estimated-time",
        action="store_true",
        help="keep DateSpan != 0 events; default is to exclude uncertain timestamps",
    )
    return p.parse_args()


def _parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            value = float(raw)
        except Exception:
            return None
        return value if pd.notna(value) else None

    text = str(raw).strip().replace(",", "")
    if not text or text.lower() in {"null", "none", "nan", "-"}:
        return None
    text = text.replace("%", "").replace("$", "")
    multiplier = 1.0
    if text and text[-1:].upper() in {"K", "M", "B", "T"}:
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[text[-1].upper()]
        text = text[:-1].strip()
    try:
        return float(text) * multiplier
    except ValueError:
        match = re.search(r"([-+]?\d*\.?\d+)\s*([KMBT]?)\s*$", text, re.I)
        if not match:
            return None
        value = float(match.group(1))
        suffix = match.group(2).upper()
        if suffix:
            value *= {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
        return value


def _numeric(record: dict[str, Any], numeric_key: str, string_key: str) -> float | None:
    value = _parse_number(record.get(numeric_key))
    if value is not None:
        return value
    return _parse_number(record.get(string_key))


def canonical_event_type(record: dict[str, Any]) -> str | None:
    hinted = str(record.get("_canonical_event_type") or "").strip().upper()
    if hinted:
        return hinted

    event = str(record.get("Event") or "").strip()
    category = str(record.get("Category") or "").strip()
    lower_event = event.lower()
    if any(
        token in lower_event
        for token in (
            "ex autos",
            "excluding autos",
            "private nonfarm",
            "adp",
            "youth unemployment",
            "u-6",
            "continuing jobless",
        )
    ):
        return None

    text = event or category
    for canonical, pattern in EVENT_RULES:
        if pattern.search(text):
            if canonical == "CPI_MOM" and "core" in lower_event:
                continue
            if canonical == "PCE_MOM" and "core" in lower_event:
                continue
            return canonical
    return None


def normalize_records(
    records: Iterable[dict[str, Any]],
    *,
    allow_estimated_time: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for record in records:
        if str(record.get("Country") or "").strip().lower() != "united states":
            continue

        event_type = canonical_event_type(record)
        if event_type is None:
            continue

        date_span = str(record.get("DateSpan") or "0").strip()
        if not allow_estimated_time and date_span not in {"", "0", "0.0"}:
            continue

        release = pd.to_datetime(record.get("Date"), utc=True, errors="coerce")
        if pd.isna(release):
            continue

        actual = _numeric(record, "ActualValue", "Actual")
        consensus = _numeric(record, "ForecastValue", "Forecast")
        previous_after_revision = _numeric(record, "PreviousValue", "Previous")
        previous_before_revision = _parse_number(record.get("Revised"))
        previous_known = (
            previous_before_revision
            if previous_before_revision is not None
            else previous_after_revision
        )
        revised_previous = previous_after_revision

        calendar_id = str(record.get("CalendarId") or "").strip()
        if not calendar_id:
            calendar_id = f"{event_type}:{release.isoformat()}:{record.get('Reference', '')}"

        rows.append(
            {
                "event_id": f"TE:{calendar_id}",
                "event_type": event_type,
                "release_time": release,
                "available_time": release,
                "actual": actual,
                "consensus": consensus,
                "previous": previous_known,
                "revised_previous": revised_previous,
                "reference": record.get("Reference"),
                "reference_date": pd.to_datetime(
                    record.get("ReferenceDate"), utc=True, errors="coerce"
                ),
                "source": record.get("Source"),
                "source_url": record.get("SourceURL"),
                "te_category": record.get("Category"),
                "te_event": record.get("Event"),
                "te_ticker": record.get("Ticker"),
                "te_symbol": record.get("Symbol"),
                "te_unit": record.get("Unit"),
                "te_currency": record.get("Currency"),
                "importance": pd.to_numeric(
                    pd.Series([record.get("Importance")]), errors="coerce"
                ).iloc[0],
                "date_span": date_span,
                "te_last_update": pd.to_datetime(
                    record.get("LastUpdate"), utc=True, errors="coerce"
                ),
                "te_forecast": _numeric(record, "TEForecastValue", "TEForecast"),
                "collector": "TRADING_ECONOMICS_CALENDAR_PIT",
                "provider_indicator": record.get("_provider_indicator"),
                "availability_policy": "OFFICIAL_RELEASE_TIME_UTC",
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "event_id",
                "event_type",
                "release_time",
                "available_time",
                "actual",
                "consensus",
                "previous",
                "revised_previous",
            ]
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["release_time", "event_id"])
        .drop_duplicates("event_id", keep="last")
        .reset_index(drop=True)
    )


def _redact_secret(message: str, secret: str) -> str:
    text = str(message)
    return text.replace(secret, "<REDACTED>") if secret else text


def _date_chunks(start: date, end: date, days: int) -> Iterable[tuple[date, date]]:
    if days < 1:
        raise ValueError("chunk days must be >= 1")
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _request_with_retries(
    session: requests.Session,
    *,
    url: str,
    params: dict[str, str],
    timeout_seconds: float,
    max_retries: int,
    api_key: str,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(url, params=params, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                payload = [payload]
            if not isinstance(payload, list):
                raise RuntimeError(
                    f"unexpected Trading Economics response type: {type(payload).__name__}"
                )
            return [dict(row) for row in payload]
        except Exception as exc:
            last_error = exc
            if attempt + 1 >= max_retries:
                break
            time.sleep(min(8.0, 1.5 * (2 ** attempt)))
    safe_error = _redact_secret(str(last_error), api_key)
    raise RuntimeError(f"Trading Economics request failed: {safe_error}") from last_error


def fetch_calendar(
    *,
    api_key: str,
    country: str,
    start: date,
    end: date,
    chunk_days: int,
    timeout_seconds: float,
    max_retries: int,
    spec: dict[str, Any],
    sleep_seconds: float = 0.10,
) -> tuple[list[dict[str, Any]], list[str]]:
    session = requests.Session()
    all_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    country_path = requests.utils.quote(country, safe="")

    for event_type, definition in spec["event_definitions"].items():
        aliases = [str(x) for x in definition.get("tradingeconomics_indicators", [])]
        if not aliases:
            warnings.append(f"{event_type}: no Trading Economics mapping; skipped")
            continue

        matched_rows: list[dict[str, Any]] = []
        selected_alias: str | None = None

        for indicator in aliases:
            indicator_path = requests.utils.quote(indicator, safe="")
            candidate_rows: list[dict[str, Any]] = []
            for d1, d2 in _date_chunks(start, end, chunk_days):
                url = (
                    f"{TE_BASE}/calendar/country/{country_path}/indicator/"
                    f"{indicator_path}/{d1.isoformat()}/{d2.isoformat()}"
                )
                payload = _request_with_retries(
                    session,
                    url=url,
                    params={"c": api_key, "f": "json", "values": "true"},
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                    api_key=api_key,
                )
                for row in payload:
                    row["_canonical_event_type"] = str(event_type)
                    row["_provider_indicator"] = indicator
                candidate_rows.extend(payload)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            candidate_rows = [
                row
                for row in candidate_rows
                if str(row.get("Country") or "").strip().lower()
                == country.strip().lower()
            ]
            if candidate_rows:
                matched_rows = candidate_rows
                selected_alias = indicator
                break

        if matched_rows:
            all_rows.extend(matched_rows)
        else:
            warnings.append(f"{event_type}: no rows from aliases={aliases!r}")

        if selected_alias and len(aliases) > 1:
            warnings.append(
                f"{event_type}: selected provider alias '{selected_alias}'"
            )

    deduped: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in all_rows:
        calendar_id = str(row.get("CalendarId") or "").strip()
        if calendar_id:
            deduped[calendar_id] = row
        else:
            anonymous.append(row)
    return list(deduped.values()) + anonymous, warnings


def main() -> int:
    args = parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"{args.api_key_env} is not set. "
            "Provide a Trading Economics API key; do not commit it to Git."
        )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise ValueError("end before start")

    spec = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    raw, warnings = fetch_calendar(
        api_key=api_key,
        country=args.country,
        start=start,
        end=end,
        chunk_days=int(args.chunk_days),
        timeout_seconds=float(args.timeout_seconds),
        max_retries=int(args.max_retries),
        spec=spec,
        sleep_seconds=float(args.sleep_seconds),
    )
    out = normalize_records(
        raw,
        allow_estimated_time=bool(args.allow_estimated_time),
    )

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        out.to_csv(output, index=False)
    else:
        out.to_parquet(output, index=False)

    status = {
        "status": "READY",
        "source": "TRADING_ECONOMICS_POINT_IN_TIME",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "raw_rows": len(raw),
        "normalized_rows": len(out),
        "event_counts": (
            out["event_type"].value_counts().sort_index().to_dict()
            if not out.empty
            else {}
        ),
        "consensus_coverage": (
            float(out["consensus"].notna().mean()) if not out.empty else 0.0
        ),
        "actual_coverage": (
            float(out["actual"].notna().mean()) if not out.empty else 0.0
        ),
        "warnings": warnings,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_key_persisted": False,
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    status_path = output.with_suffix(".status.json")
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
