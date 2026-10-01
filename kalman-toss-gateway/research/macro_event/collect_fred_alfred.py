from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

FRED_BASE = "https://api.stlouisfed.org/fred"
ET = ZoneInfo("America/New_York")

EVENT_SERIES = {
    "CPI_MOM": {"series_id": "CPIAUCSL", "release_time_et": "08:30", "transform": "pct_change"},
    "CORE_CPI_MOM": {"series_id": "CPILFESL", "release_time_et": "08:30", "transform": "pct_change"},
    "PCE_MOM": {"series_id": "PCEPI", "release_time_et": "08:30", "transform": "pct_change"},
    "CORE_PCE_MOM": {"series_id": "PCEPILFE", "release_time_et": "08:30", "transform": "pct_change"},
    "PPI_MOM": {"series_id": "PPIFID", "release_time_et": "08:30", "transform": "pct_change"},
    "NFP": {"series_id": "PAYEMS", "release_time_et": "08:30", "transform": "diff"},
    "UNEMPLOYMENT_RATE": {"series_id": "UNRATE", "release_time_et": "08:30", "transform": "diff"},
    "AHE_MOM": {"series_id": "CES0500000003", "release_time_et": "08:30", "transform": "pct_change"},
    "JOLTS_OPENINGS": {"series_id": "JTSJOL", "release_time_et": "10:00", "transform": "diff"},
    "INITIAL_CLAIMS": {"series_id": "ICSA", "release_time_et": "08:30", "transform": "diff"},
    "RETAIL_SALES_MOM": {"series_id": "RSAFS", "release_time_et": "08:30", "transform": "pct_change"},
}

RATES_SERIES = {
    "us_treasury_2y": "DGS2",
    "us_treasury_10y": "DGS10",
    "us_fed_funds_effective": "DFF",
    "us_fed_target_upper": "DFEDTARU",
    "us_fed_target_lower": "DFEDTARL",
    "us_sofr": "SOFR",
    "usdkrw": "DEXKOUS",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Collect free PIT macro events from FRED/ALFRED and daily rates context"
    )
    p.add_argument("--start", default="2017-01-01")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--events-output", required=True)
    p.add_argument("--rates-output", required=True)
    p.add_argument("--api-key-env", default="FRED_API_KEY")
    p.add_argument("--timeout-seconds", type=float, default=60.0)
    p.add_argument("--max-retries", type=int, default=4)
    return p.parse_args()


def _redact(message: str, secret: str) -> str:
    return str(message).replace(secret, "<REDACTED>") if secret else str(message)


def _request(
    session: requests.Session,
    endpoint: str,
    *,
    params: dict[str, Any],
    api_key: str,
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    url = f"{FRED_BASE}/{endpoint}"
    payload = dict(params)
    payload.update({"api_key": api_key, "file_type": "json"})
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(url, params=payload, timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"unexpected FRED response type: {type(data).__name__}")
            return data
        except Exception as exc:
            last_error = exc
            if attempt + 1 < max_retries:
                time.sleep(min(8.0, 1.5 * (2 ** attempt)))
    raise RuntimeError(
        f"FRED request failed for {endpoint}: {_redact(str(last_error), api_key)}"
    ) from last_error


def _parse_value(raw: Any) -> float:
    try:
        if raw in (None, "", "."):
            return np.nan
        return float(raw)
    except Exception:
        return np.nan


def _release_ts_utc(realtime_start: str, hhmm: str) -> pd.Timestamp:
    release_date = pd.Timestamp(realtime_start).date()
    hour, minute = (int(x) for x in hhmm.split(":"))
    local = pd.Timestamp(
        datetime.combine(release_date, dtime(hour=hour, minute=minute)),
        tz=ET,
    )
    return local.tz_convert("UTC")


def _initial_release_rows(
    session: requests.Session,
    *,
    api_key: str,
    series_id: str,
    start: date,
    end: date,
    timeout_seconds: float,
    max_retries: int,
) -> list[dict[str, Any]]:
    history_start = start - timedelta(days=400)
    data = _request(
        session,
        "series/observations",
        params={
            "series_id": series_id,
            "realtime_start": history_start.isoformat(),
            "realtime_end": end.isoformat(),
            "observation_start": history_start.isoformat(),
            "observation_end": end.isoformat(),
            "output_type": 4,
            "sort_order": "asc",
            "limit": 100000,
        },
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    rows = data.get("observations", [])
    if not isinstance(rows, list):
        raise RuntimeError(f"{series_id}: observations is not a list")
    return [dict(x) for x in rows]


def collect_events(
    *,
    api_key: str,
    start: date,
    end: date,
    timeout_seconds: float,
    max_retries: int,
) -> pd.DataFrame:
    session = requests.Session()
    rows: list[dict[str, Any]] = []

    for event_type, cfg in EVENT_SERIES.items():
        series_id = str(cfg["series_id"])
        observations = _initial_release_rows(
            session,
            api_key=api_key,
            series_id=series_id,
            start=start,
            end=end,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        for obs in observations:
            vintage = str(obs.get("realtime_start") or "").strip()
            reference = str(obs.get("date") or "").strip()
            if not vintage or not reference:
                continue
            release_date = pd.Timestamp(vintage).date()
            if release_date < start or release_date > end:
                continue
            value = _parse_value(obs.get("value"))
            if not np.isfinite(value):
                continue
            release_ts = _release_ts_utc(vintage, str(cfg["release_time_et"]))
            rows.append(
                {
                    "event_id": f"FRED:{series_id}:{reference}:{vintage}",
                    "event_type": event_type,
                    "release_time": release_ts,
                    "available_time": release_ts,
                    "actual": value,
                    "consensus": np.nan,
                    "previous": np.nan,
                    "revised_previous": np.nan,
                    "reference_date": reference,
                    "fred_series_id": series_id,
                    "release_transform": str(cfg["transform"]),
                    "source": "FRED_ALFRED_INITIAL_RELEASE",
                    "availability_policy": "ALFRED_INITIAL_RELEASE_DATE_PLUS_CANONICAL_ET_TIME",
                    "signal_basis": "INITIAL_RELEASE_CHANGE_PROXY",
                }
            )

    if not rows:
        raise RuntimeError("FRED/ALFRED initial-release collector returned no events")

    out = pd.DataFrame(rows)
    return (
        out.sort_values(["available_time", "event_type", "event_id"])
        .drop_duplicates("event_id", keep="last")
        .reset_index(drop=True)
    )


def _series_observations(
    session: requests.Session,
    *,
    api_key: str,
    series_id: str,
    start: date,
    end: date,
    timeout_seconds: float,
    max_retries: int,
) -> pd.Series:
    data = _request(
        session,
        "series/observations",
        params={
            "series_id": series_id,
            "observation_start": (start - timedelta(days=10)).isoformat(),
            "observation_end": end.isoformat(),
            "sort_order": "asc",
            "limit": 100000,
        },
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    rows = data.get("observations", [])
    index: list[pd.Timestamp] = []
    values: list[float] = []
    for obs in rows if isinstance(rows, list) else []:
        ts = pd.to_datetime(obs.get("date"), errors="coerce")
        val = _parse_value(obs.get("value"))
        if pd.isna(ts):
            continue
        index.append(pd.Timestamp(ts).normalize())
        values.append(val)
    return pd.Series(values, index=pd.DatetimeIndex(index), name=series_id, dtype=float)


def collect_rates_context(
    *,
    api_key: str,
    start: date,
    end: date,
    timeout_seconds: float,
    max_retries: int,
) -> pd.DataFrame:
    session = requests.Session()
    columns: dict[str, pd.Series] = {}
    for output_name, series_id in RATES_SERIES.items():
        columns[output_name] = _series_observations(
            session,
            api_key=api_key,
            series_id=series_id,
            start=start,
            end=end,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    frame = pd.concat(columns.values(), axis=1, join="outer").sort_index()
    frame.columns = list(columns.keys())
    frame = frame.loc[(frame.index.date >= start) & (frame.index.date <= end)].copy()

    if {"us_fed_target_upper", "us_fed_target_lower"}.issubset(frame.columns):
        frame["us_fed_target_mid"] = (
            frame["us_fed_target_upper"] + frame["us_fed_target_lower"]
        ) / 2.0
    if {"us_treasury_10y", "us_treasury_2y"}.issubset(frame.columns):
        frame["us_10y_2y_spread"] = (
            frame["us_treasury_10y"] - frame["us_treasury_2y"]
        )
    if "us_treasury_2y" in frame.columns:
        frame["us_treasury_2y_available_flag"] = frame["us_treasury_2y"].notna().astype(int)
        frame["us_treasury_2y_changed_flag"] = (
            frame["us_treasury_2y"].diff().abs().fillna(0).gt(0).astype(int)
        )

    return frame.reset_index(names="date")


def enrich_events_with_daily_2y(events: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    r = rates.copy()
    r["date"] = pd.to_datetime(r["date"], errors="coerce").dt.normalize()
    r = r.sort_values("date")
    r["us2y_daily_bp"] = pd.to_numeric(
        r["us_treasury_2y"], errors="coerce"
    ).diff() * 100.0
    lookup = r.set_index("date")["us2y_daily_bp"]
    release_dates = (
        pd.to_datetime(out["available_time"], utc=True, errors="raise")
        .dt.tz_convert(ET)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    out["us2y_daily_bp"] = release_dates.map(lookup)
    return out


def main() -> int:
    args = parse_args()
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(
            f"{args.api_key_env} is not set. Add the free FRED API key to Colab Secrets."
        )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise ValueError("end before start")

    rates = collect_rates_context(
        api_key=api_key,
        start=start,
        end=end,
        timeout_seconds=float(args.timeout_seconds),
        max_retries=int(args.max_retries),
    )
    events = collect_events(
        api_key=api_key,
        start=start,
        end=end,
        timeout_seconds=float(args.timeout_seconds),
        max_retries=int(args.max_retries),
    )
    events = enrich_events_with_daily_2y(events, rates)

    events_output = Path(args.events_output).expanduser()
    rates_output = Path(args.rates_output).expanduser()
    events_output.parent.mkdir(parents=True, exist_ok=True)
    rates_output.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(events_output, index=False)
    rates.to_parquet(rates_output, index=False)

    status = {
        "status": "READY",
        "provider": "FRED_ALFRED_FREE",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "events_rows": int(len(events)),
        "rates_rows": int(len(rates)),
        "event_counts": events["event_type"].value_counts().sort_index().to_dict(),
        "fred_series": {k: v["series_id"] for k, v in EVENT_SERIES.items()},
        "rates_series": RATES_SERIES,
        "consensus_coverage": float(events["consensus"].notna().mean()),
        "us2y_daily_coverage": float(events["us2y_daily_bp"].notna().mean()),
        "api_key_persisted": False,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    events_output.with_suffix(".status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
