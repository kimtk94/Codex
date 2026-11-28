#!/usr/bin/env python3
"""Read-only independent EOD data diagnostics for Daily20.

Cboe VIX daily-close history is the index administrator's primary publication.
Alpaca SIP closing-auction prints are venue-tagged and UNADJUSTED; they MUST
NOT be directly compared with Yahoo auto-adjusted OHLCV or promoted to a
certified composite "official close" without exchange venue/factor validation.

This collector does not require Alpaca credentials: VIX is fetched in any case,
while missing/denied SIP credentials yield explicit per-symbol HOLD statuses.
No broker endpoint, order APIs, LIVE writes, or historical file replacement.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from daily20 import load_spec, write_json

VERSION = "daily20-independent-feed-diagnostics-v1"
QUOTE_VERSION = "daily20-quote-reference-v1"
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/auctions"
NY = ZoneInfo("America/New_York")
MAX_CBOE_BYTES = 3_000_000
MAX_ALPACA_BYTES = 5_000_000
MAX_PAGES = 12
HTTP_TIMEOUT_SECONDS = 28
OFFICIAL_CLOSE_CONDITION = "M"  # Market Center Official Close (SIP condition)
RAW_ADJUSTMENT = "RAW"


def utc_time():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def bytes_sha256(blob):
    return sha256(blob).hexdigest()


def _session_window(session):
    day=date.fromisoformat(session)
    start=datetime.combine(day, datetime.min.time(), NY)
    stop=datetime.combine(day+timedelta(days=1), datetime.min.time(), NY)
    return (start.isoformat(), stop.isoformat())


def _scheduled_close_et(session):
    """Return the XNYS scheduled close, including exchange early-close sessions."""
    try:
        import exchange_calendars as xc
        import pandas as pd
        label = pd.Timestamp(date.fromisoformat(session))
        calendar = xc.get_calendar("XNYS")
        if not calendar.is_session(label):
            raise RuntimeError("AUCTION_SESSION_NOT_XNYS_SESSION")
        close = calendar.session_close(label).to_pydatetime()
        if close.tzinfo is None:
            raise RuntimeError("AUCTION_SESSION_CLOSE_UNZONED")
        return close.astimezone(NY)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("AUCTION_XNYS_CALENDAR_UNAVAILABLE") from exc


def _session_anchor(session):
    """Scheduled XNYS close label, not a claim of an observed or certified tick."""
    close = _scheduled_close_et(session)
    return close.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def http_bytes(url, headers=None, *, limit=MAX_ALPACA_BYTES):
    request=Request(url, headers={
        "User-Agent":"Kalman-Daily20-Research-Finality/1.0 (read-only)",
        "Accept":"text/csv,application/json",
        **(headers or {}),
    })
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as reply:
        if reply.status != 200:
            raise RuntimeError("SOURCE_HTTP_NOT_OK")
        raw=reply.read(limit+1)
    if not raw or len(raw)>limit:
        raise RuntimeError("SOURCE_RESPONSE_EMPTY_OR_OVERSIZE")
    return raw


def parse_cboe_csv(blob, session):
    """Cboe may prepend text/disclaimers; require a unique DATE,CLOSE header."""
    text=blob.decode("utf-8-sig")
    lines=text.splitlines()
    begins=[i for i,line in enumerate(lines)
            if line.strip().upper().replace('"',"").startswith("DATE,")]
    if len(begins)!=1:
        raise RuntimeError("CBOE_HEADER_MISSING_OR_DUPLICATED")
    reader=csv.DictReader(StringIO("\n".join(lines[begins[0]:])))
    if not reader.fieldnames:
        raise RuntimeError("CBOE_EMPTY_CSV")
    reader.fieldnames=[str(x).strip().upper() for x in reader.fieldnames]
    if not {"DATE","CLOSE"}.issubset(reader.fieldnames):
        raise RuntimeError("CBOE_PRICE_COLUMNS_MISSING")
    seen=set()
    target=None
    latest=None
    rows=0
    for row in reader:
        raw_day=str(row.get("DATE","")).strip()
        try:
            if "/" in raw_day:
                day=datetime.strptime(raw_day,"%m/%d/%Y").date()
            else:
                day=date.fromisoformat(raw_day)
        except ValueError as e:
            raise RuntimeError("CBOE_INVALID_SESSION_DATE") from e
        if day in seen:
            raise RuntimeError("CBOE_DUPLICATE_SESSION")
        seen.add(day)
        rows+=1
        latest=max(latest,day) if latest else day
        try:
            close=float(str(row["CLOSE"]).strip())
        except (ValueError,TypeError) as e:
            raise RuntimeError("CBOE_INVALID_CLOSE") from e
        if not math.isfinite(close) or close<=0:
            raise RuntimeError("CBOE_INVALID_CLOSE")
        if day.isoformat()==session:
            target=close
    if rows<1000 or not latest:
        raise RuntimeError("CBOE_UNEXPECTED_HISTORY_SHORT")
    return {"session":session,"close":target,"latest_published_session":latest.isoformat(),
            "historical_rows":rows,"body_sha256":bytes_sha256(blob)}


def _parse_timestamp(value, session):
    try:
        item=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError) as e:
        raise RuntimeError("AUCTION_INVALID_TIMESTAMP") from e
    if item.tzinfo is None:
        raise RuntimeError("AUCTION_UNZONED_TIMESTAMP")
    et=item.astimezone(NY)
    if et.date().isoformat()!=session:
        raise RuntimeError("AUCTION_WRONG_SESSION_TIMESTAMP")
    # Accept only the closing-cross timing window around the actual XNYS
    # scheduled close. This includes 13:00 ET early closes and rejects late
    # after-hours M-labelled prints.
    close_et = _scheduled_close_et(session)
    if not (close_et - timedelta(minutes=1) <= et <= close_et + timedelta(minutes=5)):
        raise RuntimeError("AUCTION_OUTSIDE_REGULAR_CLOSE_WINDOW")
    return item.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def parse_alpaca_auctions(archive, session, symbols):
    """Do not invent a primary exchange: only emit reference if all M prices agree."""
    result={}
    for symbol in symbols:
        entries=archive.get(symbol,[])
        if not isinstance(entries,list):
            raise RuntimeError("ALPACA_NOT_LIST_OF_AUCTIONS")
        target=[e for e in entries if isinstance(e,dict) and e.get("d")==session]
        if len(target)>1:
            # One symbol-day record per response is an API expectation. Treat
            # duplicates/contradictory pagination as suspect, not authority.
            result[symbol]={"status":"MULTIPLE_DAY_RECORDS_UNRESOLVED","quotes":[]}
            continue
        if not target:
            result[symbol]={"status":"NO_SESSION_AUCTIONS","quotes":[]}
            continue
        closing=target[0].get("c",[])
        if not isinstance(closing,list):
            result[symbol]={"status":"MALFORMED_CLOSING_AUCTIONS","quotes":[]}
            continue
        official=[]
        for item in closing:
            if not isinstance(item,dict) or item.get("c")!=OFFICIAL_CLOSE_CONDITION:
                continue
            price=item.get("p")
            exch=item.get("x")
            if (isinstance(price,bool) or not isinstance(price,(int,float))
                    or not math.isfinite(price) or price<=0
                    or not isinstance(exch,str) or not exch):
                continue
            try:
                timestamp=_parse_timestamp(item.get("t"),session)
            except RuntimeError:
                continue
            official.append({"price":float(price),"exchange":exch,
                             "condition":OFFICIAL_CLOSE_CONDITION,"timestamp_utc":timestamp})
        unique={(q["exchange"],q["price"],q["timestamp_utc"]):q for q in official}
        quotes=list(unique.values())
        if not quotes:
            result[symbol]={"status":"NO_VALID_MARKET_CENTER_OFFICIAL_CLOSE","quotes":[]}
            continue
        prices=[item["price"] for item in quotes]
        if max(prices)-min(prices)>0.005+1e-9:
            status="MULTI_VENUE_OFFICIAL_CLOSE_PRICES_CONFLICT"
        else:
            status="SIP_OFFICIAL_CONDITION_WITHOUT_LISTING_VENUE_CERTIFICATION"
        result[symbol]={"status":status,"quotes":quotes}
    return result


def _alpaca_credentials():
    key=os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    secret=os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    return key,secret


def fetch_alpaca(session,symbols,*,fetcher=http_bytes):
    credentials=_alpaca_credentials()
    if not all(credentials):
        return {
            "status":"CREDENTIALS_NOT_CONFIGURED",
            "origin":"Alpaca Historical Auctions SIP",
            "feed":"sip","adjustment":"RAW",
            "response_pages":0,"raw_response_sha256":[],
            "symbols":{s:{"status":"ALPACA_CREDENTIALS_UNAVAILABLE","quotes":[]}
                       for s in symbols}
        }
    begin,end=_session_window(session)
    query={"symbols":",".join(symbols),"start":begin,"end":end,
           "feed":"sip","limit":1000,"asof":session,"sort":"asc"}
    headers={"APCA-API-KEY-ID":credentials[0],
             "APCA-API-SECRET-KEY":credentials[1],
             "Accept":"application/json"}
    archive={s:[] for s in symbols}
    page_hashes=[]
    visited_tokens=set()
    try:
        for page in range(MAX_PAGES):
            url=ALPACA_URL+"?"+urlencode(query)
            response=fetcher(url,headers,limit=MAX_ALPACA_BYTES)
            page_hashes.append(bytes_sha256(response))
            data=json.loads(response)
            if not isinstance(data,dict) or not isinstance(data.get("auctions",{}),dict):
                raise RuntimeError("ALPACA_AUCTION_RESPONSE_SCHEMA_INVALID")
            for sym,items in data["auctions"].items():
                if sym not in archive or not isinstance(items,list):
                    raise RuntimeError("ALPACA_UNKNOWN_SYMBOL_OR_INVALID_AUCTIONS")
                archive[sym].extend(items)
            cursor=data.get("next_page_token")
            if not cursor:
                break
            if cursor in visited_tokens:
                raise RuntimeError("ALPACA_REPEATED_PAGE_TOKEN")
            visited_tokens.add(cursor)
            query["page_token"]=cursor
        else:
            raise RuntimeError("ALPACA_PAGINATION_NOT_EXHAUSTED")
        per_symbol=parse_alpaca_auctions(archive,session,symbols)
        overall="RESPONSE_RECEIVED_UNCERTIFIED"
        if not any(item["quotes"] for item in per_symbol.values()):
            overall="NO_AUCTION_OFFICIAL_CLOSE_QUOTES"
        return {"status":overall,"origin":"Alpaca Historical Auctions SIP",
                "feed":"sip","adjustment":"RAW",
                "response_pages":len(page_hashes),
                "raw_response_sha256":page_hashes,"symbols":per_symbol}
    except HTTPError as e:
        error="HTTP_"+str(e.code)
    except (URLError,TimeoutError) as e:
        error=type(e).__name__
    except (RuntimeError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        error=str(e)[:90]
    return {"status":"SOURCE_UNAVAILABLE",
            "reason":error,"origin":"Alpaca Historical Auctions SIP",
            "feed":"sip","adjustment":"RAW",
            "response_pages":len(page_hashes),
            "raw_response_sha256":page_hashes,
            "symbols":{s:{"status":"ALPACA_SOURCE_UNAVAILABLE","quotes":[]}
                       for s in symbols}}


def collect(session, symbols, *, fetcher=http_bytes):
    names=list(symbols)
    if len(names)!=26 or len(set(names))!=26 or "^VIX" not in names:
        raise RuntimeError("INDEPENDENT_UNIVERSE_NOT_CANONICAL_26")
    close_et=_scheduled_close_et(session)
    observed=_session_anchor(session)
    stamp=utc_time()
    sources={"^VIX":{"status":"NOT_REQUESTED","provider":"Cboe"}}
    quotes=[]
    try:
        csv_raw=fetcher(CBOE_URL,{"Accept":"text/csv"},limit=MAX_CBOE_BYTES)
        vix=parse_cboe_csv(csv_raw,session)
        if vix["close"] is None:
            sources["^VIX"]={"status":"CBOE_SESSION_NOT_PUBLISHED",
                             "provider":"Cboe","body_sha256":vix["body_sha256"],
                             "latest_published_session":vix["latest_published_session"]}
        else:
            sources["^VIX"]={"status":"CBOE_OFFICIAL_VIX_HISTORY_PRESENT",
                             "provider":"Cboe","index_admin_publication":True,
                             "body_sha256":vix["body_sha256"],
                             "latest_published_session":vix["latest_published_session"],
                             "official_index_close":vix["close"],
                             "historical_rows":vix["historical_rows"]}
            quotes.append({
                "symbol":"^VIX","quote_type":"REGULAR_CLOSE",
                "price":vix["close"],"adjustment":"RAW",
                "provider":"Cboe","feed":"VIX_Index_Historical_Daily_Close",
                "observed_at_utc":observed,"fetched_at_utc":stamp,
                "observed_timestamp_kind":"SESSION_ANCHOR_NOT_ACTUAL_TICK_TIMESTAMP",
                "source_url":CBOE_URL,
                "source_body_sha256":vix["body_sha256"],
                "independent_from_yahoo_by_origin":True,
                "independently_exchange_certified_at_16_00":False,
                "independently_exchange_certified_at_scheduled_close":False,
            })
    except HTTPError as e:
        sources["^VIX"]={"status":"CBOE_UNAVAILABLE","reason":"HTTP_"+str(e.code)}
    except (URLError,TimeoutError) as e:
        sources["^VIX"]={"status":"CBOE_UNAVAILABLE","reason":type(e).__name__}
    except (RuntimeError,ValueError,UnicodeError) as e:
        sources["^VIX"]={"status":"CBOE_UNAVAILABLE","reason":str(e)[:120]}
    equities=[s for s in names if s!="^VIX"]
    alpaca=fetch_alpaca(session,equities,fetcher=fetcher)
    for symbol,data in alpaca["symbols"].items():
        official=data["quotes"]
        if (data["status"] != "SIP_OFFICIAL_CONDITION_WITHOUT_LISTING_VENUE_CERTIFICATION"
                or not official):
            continue
        reference=official[0]
        quotes.append({
            "symbol":symbol,"quote_type":"REGULAR_CLOSE",
            "price":reference["price"],"adjustment":"RAW",
            "provider":"Alpaca","feed":"SIP_MarketCenterOfficialClose_M",
            "observed_at_utc":reference["timestamp_utc"],
            "fetched_at_utc":stamp,
            "observed_timestamp_kind":"VENUE_TAGGED_AUCTION_PRINT",
            "source_url":ALPACA_URL,
            "exchange":reference["exchange"],
            "all_observed_exchange_venues":sorted({q["exchange"] for q in official}),
            "source_body_page_sha256":alpaca["raw_response_sha256"],
            "primary_listing_exchange_independently_verified":False,
            "independently_exchange_certified_at_16_00":False,
            "independently_exchange_certified_at_scheduled_close":False,
        })
    report={
        "version":VERSION,"session":session,
        "status":"INDEPENDENT_SOURCES_DIAGNOSTIC_ONLY",
        "research_only":True,"live_execution":False,
        "production_writes":False,"strategy_promoted":False,
        "quote_type_certified":False,
        "collected_at_utc":stamp,
        "scheduled_close_et":close_et.isoformat(timespec="seconds"),
        "scheduled_close_utc":observed,
        "session_close_policy":"XNYS_CALENDAR_SESSION_CLOSE_EARLY_CLOSE_AWARE",
        "attempted":26,
        "cboe":sources["^VIX"],
        "alpaca":{
            "status":alpaca["status"],"feed":"sip",
            "response_pages":alpaca["response_pages"],
            "raw_response_sha256":alpaca["raw_response_sha256"],
            "symbols":alpaca["symbols"],
            **({"reason":alpaca["reason"]} if "reason" in alpaca else {}),
        },
        "public_reference_quotes":len(quotes),
        "public_reference_symbols":[q["symbol"] for q in quotes],
        "verified_regular_finality":0,
        "max_verified_possible_without_adjustment_and_venue_proof":0,
        "limitations":[
            "Cboe daily VIX CLOSE is an official index history, but publication does not document the exact session-clock observation time.",
            "Alpaca SIP auction prices are raw, venue-tagged, and may disagree across exchanges.",
            "Yahoo Daily20 equity/ETF close is auto-adjusted; no independent corporate-action factor is supplied here.",
            "Alpaca SIP access may require account credentials and data entitlements.",
            "A published secondary quote or a self-declared independent feed never certifies 16:00 ET close by itself.",
        ],
    }
    reference={"schema":QUOTE_VERSION,"session":session,
               "research_only":True,"quotes":quotes}
    return report,reference


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="research/kalman_daily20/universe.json")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--qc",help="Only run after source OHLCV QC has passed")
    source.add_argument("--session",help="Last completed New York session for protected credential-isolated prefetch")
    p.add_argument("--out-report",required=True)
    p.add_argument("--out-reference",required=True)
    args=p.parse_args()
    if args.qc:
        qc=json.loads(Path(args.qc).read_text())
        session=str(qc.get("expected_session"))
        if qc.get("status")!="READY" or qc.get("ready")!=26:
            raise RuntimeError("INDEPENDENT_COLLECTOR_PRIOR_QC_NOT_READY")
    else:
        session=date.fromisoformat(args.session).isoformat()
        # Isolated provider prefetch does not claim market OHLCV completeness.
        # The consuming research job MUST enforce exact-session QC equivalence.
    spec=load_spec(args.config)
    report,reference=collect(session,spec["core"]+spec["context"])
    write_json(args.out_report,report)
    write_json(args.out_reference,reference)
    print(json.dumps({"DAILY20_INDEPENDENT_MARKET_SOURCES":{
        "session":session,"CBOE":report["cboe"]["status"],
        "Alpaca_SIP":report["alpaca"]["status"],
        "quotes":len(reference["quotes"]),
        "certified_finality":0,"required":26,
    }}))


if __name__=="__main__":
    main()
