#!/usr/bin/env python3
"""Private Alpaca SIP 15m research backfill, never touches live market state."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests
import exchange_calendars as xcals

URL = "https://data.alpaca.markets/v2/stocks/bars"
SYMBOLS = ("QLD", "QQQ")
TZ = "America/New_York"
START = "2024-01-01"
END_EXCLUSIVE = "2026-10-31"
ADJUSTMENT = "all"


class ProviderError(RuntimeError):
    pass


def safe_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def credentials():
    k = (os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID") or "").strip()
    s = (os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or "").strip()
    return (k, s) if k and s else None


def request_page(session, key, secret, params, max_retries=3):
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    for attempt in range(max_retries):
        try:
            response = session.get(URL, params=params, headers=headers, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt + 1 >= max_retries:
                raise ProviderError("NETWORK_" + type(exc).__name__) from None
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            if attempt + 1 < max_retries:
                # bounded retry only; never print response body or credential headers
                delay = min(12, max(1., float(response.headers.get("Retry-After", "2"))))
                time.sleep(delay)
                continue
        if response.status_code != 200:
            raise ProviderError("ALPACA_HTTP_" + str(response.status_code))
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("ALPACA_BAD_JSON") from None
        if not isinstance(data, dict) or not isinstance(data.get("bars"), dict):
            raise ProviderError("ALPACA_BAD_SCHEMA")
        return data
    raise ProviderError("ALPACA_RETRY_EXHAUSTED")


def month_ranges(start, end):
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start >= end:
        raise ValueError("INVALID_START_END")
    cursor = start
    while cursor < end:
        nxt = min(cursor + pd.offsets.MonthBegin(1), end)
        yield cursor, nxt
        cursor = nxt


def download(session, key, secret, start, end, max_pages_per_month=30):
    raw = []
    pages = 0
    for a, b in month_ranges(start, end):
        token = None
        seen = set()
        for _ in range(max_pages_per_month):
            query = {"symbols": ",".join(SYMBOLS), "timeframe": "15Min",
                     "start": a.strftime("%Y-%m-%dT00:00:00Z"),
                     "end": b.strftime("%Y-%m-%dT00:00:00Z"),
                     "feed": "sip", "adjustment": ADJUSTMENT,
                     "limit": 10000, "sort": "asc"}
            if token:
                query["page_token"] = token
            result = request_page(session, key, secret, query)
            pages += 1
            for sym in SYMBOLS:
                bars = result["bars"].get(sym, [])
                if not isinstance(bars, list):
                    raise ProviderError("ALPACA_BAD_SYMBOL_SCHEMA")
                for item in bars:
                    if not isinstance(item, dict):
                        raise ProviderError("ALPACA_BAD_BAR")
                    raw.append({"market": sym, "candle_time_utc": item.get("t"),
                                "open": item.get("o"), "high": item.get("h"),
                                "low": item.get("l"), "close": item.get("c"),
                                "volume": item.get("v"), "unit_min": 15})
            token = result.get("next_page_token")
            if not token:
                break
            if token in seen:
                raise ProviderError("ALPACA_PAGE_TOKEN_LOOP")
            seen.add(token)
        else:
            raise ProviderError("ALPACA_MAX_PAGES_REACHED")
    if not raw:
        raise ProviderError("ALPACA_ZERO_BARS")
    frame = pd.DataFrame(raw)
    ts = pd.to_datetime(frame.candle_time_utc, utc=True, errors="coerce")
    if ts.isna().any() or frame.duplicated(["market", "candle_time_utc"]).any():
        raise ProviderError("BAD_TIMESTAMP_OR_DUPLICATE")
    for c in ("open", "high", "low", "close"):
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    p = frame[["open", "high", "low", "close"]]
    if not np.isfinite(p.to_numpy()).all() or (p <= 0).any().any():
        raise ProviderError("NON_FINITE_OR_NONPOSITIVE_OHLC")
    if (frame.high < frame[["open", "low", "close"]].max(axis=1)).any() or (
        frame.low > frame[["open", "high", "close"]].min(axis=1)).any():
        raise ProviderError("INCONSISTENT_OHLC")
    frame = frame.sort_values(["market", "candle_time_utc"]).reset_index(drop=True)
    return frame, pages


def coverage(frame, start, end):
    cal = xcals.get_calendar("XNYS")
    dates = cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=1))
    result, complete = {}, {}
    for symbol in SYMBOLS:
        sub = frame.loc[frame.market.eq(symbol)].copy()
        sub["ts"] = pd.to_datetime(sub.candle_time_utc, utc=True).dt.tz_convert(TZ)
        sub["session"] = pd.to_datetime(sub.ts.dt.strftime("%Y-%m-%d"))
        by_session = {k: v.reset_index(drop=True) for k, v in sub.groupby("session")}
        missing_hours = Counter()
        complete_by_year = Counter()
        partial_by_year = Counter()
        missing_by_year = Counter()
        for day in dates:
            session = pd.Timestamp(day).tz_localize(None)
            open_time = cal.session_open(day).tz_convert(TZ)
            close_time = cal.session_close(day).tz_convert(TZ)
            expected = pd.date_range(open_time, close_time - pd.Timedelta(minutes=15),
                                     freq="15min")
            g = by_session.get(session)
            if g is None:
                missing_by_year[str(day.year)] += 1
                continue
            actual = g.loc[g.ts.ge(open_time) & g.ts.lt(close_time)].reset_index(drop=True)
            if pd.DatetimeIndex(actual.ts).equals(expected):
                complete[(symbol, session)] = actual
                complete_by_year[str(day.year)] += 1
                continue
            partial_by_year[str(day.year)] += 1
            for dt in expected.difference(pd.DatetimeIndex(actual.ts)):
                missing_hours[dt.strftime("%H:%M")] += 1
        result[symbol] = {
            "bars": int(len(sub)), "complete_by_year": dict(complete_by_year),
            "partial_by_year": dict(partial_by_year),
            "missing_by_year": dict(missing_by_year),
            "missing_slot_top10": missing_hours.most_common(10),
            "total_sessions": int(len(dates)),
            "complete_sessions": int(sum(complete_by_year.values()))
        }
    return result, complete, dates


def make_daily(complete, dates):
    rows = []
    for d in dates:
        d = pd.Timestamp(d).tz_localize(None)
        qld = complete.get(("QLD", d))
        qqq = complete.get(("QQQ", d))
        # Keep full exchange-session calendar; leave missing sessions NA rather than
        # pretending a 4-session horizon has only observed trading dates.
        rows.append({"date_ny": d.strftime("%Y-%m-%d"),
                     "close_qld": float(qld.iloc[-1].close) if qld is not None else np.nan,
                     "close_qqq": float(qqq.iloc[-1].close) if qqq is not None else np.nan})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START)
    ap.add_argument("--end-exclusive", default=END_EXCLUSIVE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--probe-only", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    status = {"status": "INIT", "provider": "Alpaca", "feed": "SIP",
              "adjustment": ADJUSTMENT, "symbols": list(SYMBOLS),
              "start": a.start, "end_exclusive": a.end_exclusive,
              "no_live_trading": True, "no_production_writes": True,
              "no_raw_bars_in_public_artifact": True,
              "recorded_at_utc": datetime.now(timezone.utc).isoformat()}
    auth = credentials()
    if not auth:
        status.update(status="BLOCKED", reason="ALPACA_CI_SECRETS_NOT_CONFIGURED")
        safe_json(out/"status.json", status)
        print(json.dumps(status))
        raise SystemExit(2)
    with requests.Session() as session:
        try:
            # A historical, completed session only; never require paid real-time SIP.
            probe, pcount = download(session, *auth, "2024-01-03", "2024-01-04", 3)
            if set(probe.market.unique()) != set(SYMBOLS):
                raise ProviderError("PROBE_MISSING_SYMBOL")
            status["probe"] = "SIP_OK"
            status["probe_bar_count"] = int(len(probe))
            if a.probe_only:
                status["status"] = "PROBE_PASS"
                safe_json(out/"status.json", status)
                print(json.dumps(status))
                return
            bars, pages = download(session, *auth, a.start, a.end_exclusive)
            audit, complete, dates = coverage(bars, a.start, a.end_exclusive)
            daily = make_daily(complete, dates)
            status.update(pages=pages, coverage=audit,
                          common_complete_sessions=int(daily[["close_qld","close_qqq"]].notna().all(axis=1).sum()),
                          missing_daily_sessions=int(daily[["close_qld","close_qqq"]].isna().any(axis=1).sum()))
            # Require large, unbroken historical training and test cohorts.
            for y in (2024, 2025):
                if any(audit[s]["complete_by_year"].get(str(y), 0) < 200 for s in SYMBOLS):
                    raise ProviderError("COVERAGE_INSUFFICIENT_" + str(y))
            # For 2026 partial through October, require >=150 complete sessions.
            if any(audit[s]["complete_by_year"].get("2026", 0) < 150 for s in SYMBOLS):
                raise ProviderError("COVERAGE_INSUFFICIENT_2026")
            bars.to_parquet(out/"qld_qqq_15m_sip_all_private.parquet", index=False)
            daily.to_csv(out/"qld_qqq_daily_sip_all_private.csv", index=False)
            status["status"] = "READY_RESEARCH_ONLY"
        except ProviderError as exc:
            status.update(status="HOLD", reason=str(exc))
            safe_json(out/"status.json", status)
            print(json.dumps(status, ensure_ascii=False))
            raise SystemExit(2) from None
    safe_json(out/"status.json", status)
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
