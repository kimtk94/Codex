from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
import psycopg


UTC = timezone.utc
TE_BASE_URL = "https://api.tradingeconomics.com"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


class PublicCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.row_depth = 0
        self.outer_td_index = -1
        self.active_td: int | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(k): str(v or "") for k, v in attrs}

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        a = self._attrs(attrs)
        if tag == "tr":
            if self.current is None:
                if a.get("data-country", "").strip().lower() != "united states":
                    return
                self.current = {
                    "CalendarId": a.get("data-id") or None,
                    "Country": "United States",
                    "Category": a.get("data-category") or "",
                    "Event": a.get("data-event") or "",
                    "Symbol": a.get("data-symbol") or "",
                    "Ticker": a.get("data-symbol") or "",
                    "Url": a.get("data-url") or "",
                    "cells": {},
                    "date": None,
                }
                self.row_depth = 1
                self.outer_td_index = -1
                self.active_td = None
                return
            self.row_depth += 1
            return

        if self.current is None:
            return

        if tag == "td" and self.row_depth == 1:
            self.outer_td_index += 1
            self.active_td = self.outer_td_index
            self.current["cells"].setdefault(self.active_td, [])
            classes = a.get("class", "")
            match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", classes)
            if self.outer_td_index == 0 and match:
                self.current["date"] = match.group(1)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.current is None:
            return
        if tag == "td" and self.row_depth == 1:
            self.active_td = None
            return
        if tag == "tr":
            self.row_depth -= 1
            if self.row_depth == 0:
                cells = {
                    idx: " ".join(" ".join(parts).split())
                    for idx, parts in self.current["cells"].items()
                }
                self.current["cells"] = cells
                self.rows.append(self.current)
                self.current = None
                self.active_td = None
                self.outer_td_index = -1

    def handle_data(self, data: str) -> None:
        if (
            self.current is not None
            and self.row_depth == 1
            and self.active_td is not None
        ):
            text = str(data or "").strip()
            if text:
                self.current["cells"][self.active_td].append(text)


def parse_public_calendar_html(html: str) -> list[dict[str, Any]]:
    parser = PublicCalendarParser()
    parser.feed(html)
    rows: list[dict[str, Any]] = []
    for raw in parser.rows:
        date_text = str(raw.get("date") or "").strip()
        cells = raw.get("cells") or {}
        time_text = str(cells.get(0) or "").strip()
        if not date_text or not time_text:
            continue
        try:
            release_at = datetime.strptime(
                f"{date_text} {time_text}",
                "%Y-%m-%d %I:%M %p",
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
        rows.append(
            {
                "CalendarId": raw.get("CalendarId"),
                "Date": release_at.isoformat(),
                "Country": "United States",
                "Category": raw.get("Category"),
                "Event": raw.get("Event"),
                "Symbol": raw.get("Symbol"),
                "Ticker": raw.get("Ticker"),
                "Actual": cells.get(3) or None,
                "Previous": cells.get(4) or None,
                "Forecast": cells.get(5) or None,
                "TEForecast": cells.get(6) or None,
                "Source": "Trading Economics public calendar",
                "SourceURL": "https://tradingeconomics.com/united-states/calendar",
                "DateSpan": "0",
                "PublicCalendarSnapshot": True,
            }
        )
    return rows


def parse_calendar_value(value: Any, target_unit: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()

    cleaned = (
        text.replace(",", "")
        .replace("%", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .strip()
    )
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([KMBT]?)", cleaned, re.I)
    if not match:
        return None

    number = float(match.group(1))
    suffix = match.group(2).upper()
    if negative:
        number = -abs(number)

    target = (target_unit or "").strip().lower()
    if target == "thousands":
        multiplier = {"": 1.0, "K": 1.0, "M": 1000.0, "B": 1_000_000.0, "T": 1_000_000_000.0}
    else:
        multiplier = {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0, "T": 1_000_000_000_000.0}
    return number * multiplier[suffix]


def _provider_market_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    provider = config.get("trading_economics") or {}
    markets = provider.get("markets")
    if isinstance(markets, dict) and markets:
        out: list[dict[str, Any]] = []
        for market, raw_spec in markets.items():
            if not isinstance(raw_spec, dict):
                continue
            spec = {
                key: value
                for key, value in provider.items()
                if key != "markets"
            }
            spec.update(raw_spec)
            spec["market"] = str(market).upper()
            out.append(spec)
        return out

    # Backward-compatible single-market contract used by v1.6 and tests.
    legacy = dict(provider)
    legacy["market"] = str(legacy.get("market") or "US").upper()
    return [legacy]


def event_indicator_key(
    row: dict[str, Any],
    config: dict[str, Any],
    market_spec: dict[str, Any] | None = None,
) -> str | None:
    provider = config.get("trading_economics") or {}
    spec = market_spec or provider
    mapping = spec.get("event_map") or provider.get("event_map") or {}
    candidates = [
        _norm_text(row.get("Event")),
        _norm_text(row.get("Category")),
        _norm_text(row.get("Ticker")),
        _norm_text(row.get("Symbol")),
    ]
    normalized_map = {_norm_text(k): str(v) for k, v in mapping.items()}
    for candidate in candidates:
        if candidate in normalized_map:
            return normalized_map[candidate]
    return None


def normalize_calendar_row(
    row: dict[str, Any],
    config: dict[str, Any],
    as_of: datetime,
    market_spec: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    provider = config.get("trading_economics") or {}
    spec = market_spec or provider
    market = str(spec.get("market") or "US").upper()
    indicator_key = event_indicator_key(row, config, spec)
    if not indicator_key:
        return None

    normalization = config.get("indicator_normalization") or {}
    indicator_spec = normalization.get(indicator_key) or {}
    target_unit = str(indicator_spec.get("unit") or "").strip() or None

    release_at = parse_dt(row.get("Date"))
    if release_at is None:
        return None

    actual_raw = parse_calendar_value(row.get("Actual"), target_unit)
    consensus_raw = parse_calendar_value(row.get("Forecast"), target_unit)
    previous = parse_calendar_value(row.get("Previous"), target_unit)
    snapshot_phase = "PRE_RELEASE" if as_of < release_at else "POST_RELEASE"

    if snapshot_phase == "PRE_RELEASE":
        if consensus_raw is None:
            return None
        actual = None
        consensus = consensus_raw
        available_at = release_at
    else:
        if actual_raw is None:
            return None
        actual = actual_raw
        consensus = None
        last_update = parse_dt(row.get("LastUpdate"))
        if row.get("PublicCalendarSnapshot"):
            available_at = as_of
        else:
            available_at = (
                max(release_at, last_update)
                if last_update
                else max(release_at, as_of)
            )
        if available_at > as_of:
            return None

    calendar_id = str(row.get("CalendarId") or row.get("CalendarID") or "").strip()
    event_name = str(row.get("Event") or row.get("Category") or indicator_key).strip()
    source_item_id = (
        calendar_id
        or str(row.get("Ticker") or row.get("Symbol") or "").strip()
        or None
    )

    material = "|".join(
        [
            market,
            indicator_key,
            event_name,
            release_at.isoformat(),
            source_item_id or "",
            "trading_economics_calendar",
        ]
    )
    observation_id = "te-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]

    date_span = str(row.get("DateSpan") or "0").strip()
    time_quality = "PROVIDER_RELEASE_TS" if date_span == "0" else "PROVIDER_ESTIMATED_TS"

    payload = {
        "provider": (
            "trading_economics_public_calendar"
            if row.get("PublicCalendarSnapshot")
            else "trading_economics"
        ),
        "consensus_snapshot_phase": snapshot_phase,
        "post_release_consensus_ignored": (
            consensus_raw is not None and snapshot_phase == "POST_RELEASE"
        ),
        "market": market,
        "calendar_id": calendar_id or None,
        "country": row.get("Country"),
        "category": row.get("Category"),
        "event": row.get("Event"),
        "reference": row.get("Reference"),
        "reference_date": row.get("ReferenceDate"),
        "source": row.get("Source"),
        "source_url": row.get("SourceURL"),
        "te_forecast": row.get("TEForecast"),
        "importance": row.get("Importance"),
        "ticker": row.get("Ticker"),
        "symbol": row.get("Symbol"),
        "raw_unit": row.get("Unit"),
        "last_update": row.get("LastUpdate"),
    }
    if snapshot_phase == "PRE_RELEASE":
        payload["consensus_captured_at"] = as_of.isoformat()
    elif row.get("PublicCalendarSnapshot"):
        payload["actual_first_seen_at"] = as_of.isoformat()

    return {
        "observation_id": observation_id,
        "indicator_key": indicator_key,
        "event_name": event_name,
        "market": market,
        "release_at": release_at,
        "available_at": available_at,
        "actual": actual,
        "consensus": consensus,
        "previous": previous,
        "unit": target_unit or str(row.get("Unit") or "").strip() or None,
        "source": "trading_economics_calendar",
        "source_item_id": source_item_id,
        "time_quality": time_quality,
        "payload": payload,
    }


def sanitize_provider_error(exc: Exception, credentials: str) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if credentials:
        message = message.replace(credentials, "***")
        message = message.replace(quote(credentials, safe=""), "***")
    return message


def _minutes(text: str) -> int:
    hh, mm = str(text).split(":", 1)
    return int(hh) * 60 + int(mm)


def _minute_in_window(current: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= current <= end
    # Supports an overnight local-time window.
    return current >= start or current <= end


def within_active_window(as_of: datetime, provider: dict[str, Any]) -> bool:
    timezone_name = str(provider.get("timezone") or "").strip()
    local_windows = provider.get("active_windows_local")
    if timezone_name and isinstance(local_windows, list) and local_windows:
        try:
            local = as_of.astimezone(ZoneInfo(timezone_name))
        except Exception:
            return False
        weekdays = set(
            int(x) for x in provider.get("active_weekdays", [0, 1, 2, 3, 4])
        )
        if local.weekday() not in weekdays:
            return False
        current = local.hour * 60 + local.minute
        for window in local_windows:
            if not isinstance(window, dict):
                continue
            try:
                start = _minutes(str(window.get("start", "00:00")))
                end = _minutes(str(window.get("end", "23:59")))
            except (TypeError, ValueError):
                continue
            if _minute_in_window(current, start, end):
                return True
        return False

    # Legacy v1.6 UTC window contract.
    weekdays = set(int(x) for x in provider.get("active_weekdays", [0, 1, 2, 3, 4]))
    now = as_of.astimezone(UTC)
    if now.weekday() not in weekdays:
        return False
    window = provider.get("active_window_utc") or {}
    try:
        start = _minutes(str(window.get("start", "12:00")))
        end = _minutes(str(window.get("end", "16:15")))
    except (TypeError, ValueError):
        return False
    current = now.hour * 60 + now.minute
    return _minute_in_window(current, start, end)


def fetch_public_calendar_rows(
    config: dict[str, Any],
    as_of: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider = config.get("trading_economics") or {}
    public = provider.get("public_calendar_fallback") or {}
    if not public.get("enabled", False):
        return [], {
            "status": "PUBLIC_FALLBACK_DISABLED",
            "rows_seen": 0,
            "rows_mapped": 0,
        }

    us_spec = None
    for spec in _provider_market_specs(config):
        if str(spec.get("market") or "").upper() == "US":
            us_spec = spec
            break
    if us_spec is None:
        return [], {
            "status": "PUBLIC_FALLBACK_US_UNCONFIGURED",
            "rows_seen": 0,
            "rows_mapped": 0,
        }
    if not within_active_window(as_of, us_spec):
        return [], {
            "status": "OUTSIDE_ACTIVE_WINDOW",
            "rows_seen": 0,
            "rows_mapped": 0,
            "provider": "trading_economics_public_calendar",
        }

    url = str(
        public.get("url")
        or "https://tradingeconomics.com/united-states/calendar"
    )
    try:
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
            raw_rows = parse_public_calendar_html(response.text)

        mapped: list[dict[str, Any]] = []
        for row in raw_rows:
            normalized = normalize_calendar_row(
                row,
                config,
                as_of,
                us_spec,
            )
            if normalized is not None:
                mapped.append(normalized)

        return mapped, {
            "status": "READY",
            "rows_seen": len(raw_rows),
            "rows_mapped": len(mapped),
            "provider": "trading_economics_public_calendar",
            "market_status": {
                "US": {
                    "status": "READY",
                    "rows_seen": len(raw_rows),
                    "rows_mapped": len(mapped),
                },
                "KR": {
                    "status": "UNAVAILABLE_NO_PUBLIC_FALLBACK",
                    "rows_seen": 0,
                    "rows_mapped": 0,
                },
            },
        }
    except Exception as exc:
        return [], {
            "status": "PUBLIC_FALLBACK_ERROR",
            "rows_seen": 0,
            "rows_mapped": 0,
            "provider": "trading_economics_public_calendar",
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_calendar_rows(
    config: dict[str, Any],
    as_of: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider = config.get("trading_economics") or {}
    if not provider.get("enabled", True):
        return [], {"status": "DISABLED_CONFIG", "rows_seen": 0, "rows_mapped": 0}
    runtime_default = bool(provider.get("runtime_enabled_default", False))
    if not env_bool("KALMAN_MACRO_CONSENSUS_ENABLED", runtime_default):
        return [], {"status": "DISABLED_RUNTIME", "rows_seen": 0, "rows_mapped": 0}

    credentials = (os.environ.get("TRADING_ECONOMICS_API_KEY") or "").strip()
    if not credentials or credentials.lower() in {"guest", "guest:guest"}:
        primary_status = (
            "UNCONFIGURED"
            if not credentials
            else "DEMO_CREDENTIALS_REJECTED"
        )
        if bool((provider.get("public_calendar_fallback") or {}).get("enabled")):
            rows, status = fetch_public_calendar_rows(config, as_of)
            return rows, {
                **status,
                "primary_provider": "trading_economics_authenticated_api",
                "primary_provider_status": primary_status,
                "fallback_used": True,
            }
        return [], {
            "status": primary_status,
            "rows_seen": 0,
            "rows_mapped": 0,
            "provider": "trading_economics",
        }

    days = max(1, int(provider.get("lookback_days", 5)))
    start = (as_of - timedelta(days=days)).date().isoformat()
    end = as_of.date().isoformat()
    base_url = str(provider.get("base_url", TE_BASE_URL)).rstrip("/")
    timeout_seconds = float(provider.get("timeout_seconds", 20))

    all_rows: list[dict[str, Any]] = []
    market_status: dict[str, dict[str, Any]] = {}
    total_seen = 0
    total_mapped = 0
    attempted = 0
    ready = 0
    errors = 0

    for spec in _provider_market_specs(config):
        market = str(spec.get("market") or "US").upper()
        country = str(spec.get("country") or "").strip()
        if not country:
            market_status[market] = {
                "status": "UNCONFIGURED_COUNTRY",
                "rows_seen": 0,
                "rows_mapped": 0,
            }
            continue
        if not within_active_window(as_of, spec):
            market_status[market] = {
                "status": "OUTSIDE_ACTIVE_WINDOW",
                "rows_seen": 0,
                "rows_mapped": 0,
                "country": country,
            }
            continue

        attempted += 1
        url = f"{base_url}/calendar/country/{quote(country, safe='')}/{start}/{end}"
        params = {
            "c": credentials,
            "f": "json",
            "values": "true",
        }
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Trading Economics calendar response is not a list")

            mapped: list[dict[str, Any]] = []
            for row in payload:
                if not isinstance(row, dict):
                    continue
                country_value = _norm_text(row.get("Country"))
                if country_value and country_value != _norm_text(country):
                    continue
                normalized = normalize_calendar_row(row, config, as_of, spec)
                if normalized is not None:
                    mapped.append(normalized)

            seen_count = len(payload)
            mapped_count = len(mapped)
            total_seen += seen_count
            total_mapped += mapped_count
            all_rows.extend(mapped)
            ready += 1
            market_status[market] = {
                "status": "READY",
                "rows_seen": seen_count,
                "rows_mapped": mapped_count,
                "country": country,
                "window_start": start,
                "window_end": end,
            }
        except Exception as exc:
            errors += 1
            market_status[market] = {
                "status": "ERROR",
                "rows_seen": 0,
                "rows_mapped": 0,
                "country": country,
                "error": sanitize_provider_error(exc, credentials),
            }

    if ready:
        overall = "DEGRADED" if errors else "READY"
    elif attempted and errors:
        public_rows, public_status = fetch_public_calendar_rows(config, as_of)
        return public_rows, {
            **public_status,
            "primary_provider": "trading_economics_authenticated_api",
            "primary_provider_status": "ERROR",
            "primary_market_status": market_status,
            "fallback_used": True,
        }
    else:
        overall = "OUTSIDE_ACTIVE_WINDOW"

    return all_rows, {
        "status": overall,
        "rows_seen": total_seen,
        "rows_mapped": total_mapped,
        "provider": "trading_economics",
        "window_start": start,
        "window_end": end,
        "market_status": market_status,
    }


def upsert_observations(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    seen = inserted = updated = 0
    for row in rows:
        seen += 1
        result = conn.execute(
            """
            INSERT INTO public.macro_release_observation AS mro(
              observation_id,indicator_key,event_name,market,
              release_at,available_at,actual,consensus,previous,
              unit,source,source_item_id,time_quality,payload,updated_at
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            ON CONFLICT(observation_id) DO UPDATE SET
              actual=COALESCE(
                excluded.actual,
                mro.actual
              ),
              consensus=CASE
                WHEN excluded.payload->>'consensus_snapshot_phase' = 'PRE_RELEASE'
                     AND excluded.consensus IS NOT NULL
                THEN excluded.consensus
                ELSE mro.consensus
              END,
              previous=COALESCE(
                excluded.previous,
                mro.previous
              ),
              available_at=GREATEST(
                mro.available_at,
                excluded.available_at
              ),
              payload=mro.payload || excluded.payload,
              updated_at=now()
            RETURNING (xmax = 0) AS inserted
            """,
            (
                row["observation_id"],
                row["indicator_key"],
                row["event_name"],
                row["market"],
                row["release_at"],
                row["available_at"],
                row["actual"],
                row["consensus"],
                row["previous"],
                row["unit"],
                row["source"],
                row["source_item_id"],
                row["time_quality"],
                json.dumps(row["payload"], ensure_ascii=False, sort_keys=True),
            ),
        ).fetchone()
        if isinstance(result, dict):
            was_inserted = bool(result.get("inserted"))
        else:
            was_inserted = bool(result and result[0])
        inserted += int(was_inserted)
        updated += int(not was_inserted)
    return {"seen": seen, "inserted": inserted, "updated": updated}


def refresh_consensus_observations(
    conn: psycopg.Connection,
    config: dict[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    rows, status = fetch_calendar_rows(config, as_of)
    if status.get("status") not in {"READY", "DEGRADED"}:
        return status
    counts = upsert_observations(conn, rows)
    conn.commit()
    return {**status, **counts}
