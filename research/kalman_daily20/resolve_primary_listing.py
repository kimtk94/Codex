#!/usr/bin/env python3
"""Provider-declared primary listing versus SIP official market-center close.

Read-only point-in-time research evidence. Uses authenticated existing Alpaca
Asset master and SIP exchange code registry, fetched in the protected job,
never the trading/order API. Alpaca's CURRENT master is not a certified
historical listing registry. For dated session signals, all selected prices
remain uncategorically research-only and RAW, incomparable to Yahoo's
auto-adjusted close without separately authenticated corporate actions.

Never "vote" across P/N/Q/T or choose the M quote closest to Yahoo.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from collect_independent_close import http_bytes, utc_time
from daily20 import load_spec, write_json

VERSION="daily20-primary-listing-evidence-v1"
QUOTES_VERSION="daily20-quote-reference-v1"
ASSET_ENDPOINT="https://paper-api.alpaca.markets/v2/assets/"
EXCHANGE_ENDPOINT="https://data.alpaca.markets/v2/stocks/meta/exchanges"
MAX_SINGLE_ASSET_BYTES=30_000
MAX_META_BYTES=100_000

# Restricted to specific exact security listing venues. Market centers may
# have multiple near-identical names; do not mistake their branches for primary.
def canonical_exchange(value):
    if not isinstance(value,str):
        return None
    name=re.sub(r"[^A-Z0-9]+"," ",value.upper()).strip()
    if any(bad in name for bad in ("OPTION", "TRF", "FINRA","CHICAGO",
                                    "TEXAS","PACIFIC","BX","PSX","PHLX","MEMX")):
        return None
    # The authenticated SIP exchange registry calls Q "NASDAQ OMX".
    # "NASDAQ Int" / T is a DIFFERENT venue and remains unsupported.
    if name in ("NASDAQ","NASDAQ OMX","NASDAQ STOCK MARKET",
                "THE NASDAQ STOCK MARKET","NASDAQ GLOBAL SELECT MARKET"):
        return "NASDAQ"
    if name in ("NYSE","NEW YORK STOCK EXCHANGE","NYSE STOCK EXCHANGE"):
        return "NYSE"
    if name in ("ARCA","NYSEARCA","NYSE ARCA","NYSE ARCA INC"):
        return "NYSE_ARCA"
    if name in ("BATS","BZX","BATS BZX EXCHANGE","CBOE BZX EXCHANGE"):
        return "CBOE_BZX"
    if name in ("AMEX","NYSE AMERICAN","NYSE AMERICAN LLC"):
        return "NYSE_AMERICAN"
    return None


def _typed_metadata_map(payload):
    if isinstance(payload,dict):
        if "exchanges" in payload:
            return _typed_metadata_map(payload["exchanges"])
        items=list(payload.items())
        if not all(isinstance(k,str) and isinstance(v,str) for k,v in items):
            raise RuntimeError("VENUE_METADATA_UNEXPECTED_MAPPING")
        return {k.upper():v for k,v in items}
    if isinstance(payload,list):
        names={}
        for obj in payload:
            if not isinstance(obj,dict):
                raise RuntimeError("VENUE_METADATA_WRONG_ROW")
            k=obj.get("code",obj.get("id"))
            v=obj.get("name",obj.get("description"))
            if not isinstance(k,str) or not isinstance(v,str) or k.upper() in names:
                raise RuntimeError("VENUE_METADATA_WRONG_ROW")
            names[k.upper()]=v
        return names
    raise RuntimeError("VENUE_METADATA_NOT_MAP")


def resolve(exchange, meta, quotes):
    """Select only exact venue official M price when code is unambiguous."""
    canonical=canonical_exchange(exchange)
    if canonical is None:
        return {"status":"ASSET_EXCHANGE_UNSUPPORTED","canonical":None,
                "venue_codes":[],"selected":None}
    codes=[code for code,name in meta.items()
           if canonical_exchange(name)==canonical]
    # Restrict code correspondence to exactly one code, rather than silently
    # prefer a more convenient observed/price-matching venue.
    if len(codes)!=1:
        return {"status":("EXCHANGE_CODE_NOT_FOUND" if not codes else
                          "EXCHANGE_CODE_AMBIGUOUS"),
                "canonical":canonical,"venue_codes":sorted(codes),"selected":None}
    code=codes[0]
    candidates=[entry for entry in quotes if entry.get("exchange")==code
                and entry.get("condition")=="M"]
    if not candidates:
        return {"status":"PRIMARY_VENUE_M_PRINT_MISSING","canonical":canonical,
                "venue_codes":[code],"selected":None}
    if len(candidates)!=1:
        return {"status":"PRIMARY_VENUE_MULTIPLE_M_PRINTS","canonical":canonical,
                "venue_codes":[code],"selected":None}
    return {"status":"PROVIDER_DECLARED_PRIMARY_M_PRINT_RESEARCH_ONLY",
            "canonical":canonical,"venue_codes":[code],
            "selected":candidates[0]}


def _headers():
    k=os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    s=os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    return ({"APCA-API-KEY-ID":k,"APCA-API-SECRET-KEY":s,
             "Accept":"application/json"} if k and s else None)


def _http_status(exc):
    if isinstance(exc,HTTPError):
        return "HTTP_"+str(exc.code)
    if isinstance(exc,URLError):
        return "NETWORK_UNAVAILABLE"
    return type(exc).__name__


def fetch_assets(symbols, *, fetcher=http_bytes):
    """GET asset metadata only; store sha and listing field, not raw responses."""
    headers=_headers()
    if headers is None:
        return {s:{"status":"CREDENTIALS_NOT_CONFIGURED"} for s in symbols}
    out={}
    for symbol in symbols:
        url=ASSET_ENDPOINT+quote(symbol,safe="")
        try:
            raw=fetcher(url,headers,limit=MAX_SINGLE_ASSET_BYTES)
            item=json.loads(raw)
            if not isinstance(item,dict) or item.get("symbol")!=symbol:
                out[symbol]={"status":"ASSET_IDENTITY_MISMATCH"}
                continue
            exch=item.get("exchange")
            if not isinstance(exch,str) or not exch.strip():
                out[symbol]={"status":"ASSET_EXCHANGE_NOT_REPORTED"}
                continue
            out[symbol]={
                "status":"ASSET_MASTER_LIST_RETRIEVED",
                "exchange":exch,
                "active":item.get("status")=="active",
                "asset_id":item.get("id") if isinstance(item.get("id"),str) else None,
                "metadata_sha256":sha256(raw).hexdigest(),
            }
        except (HTTPError,URLError,TimeoutError) as exc:
            out[symbol]={"status":"ASSET_LOOKUP_UNAVAILABLE",
                         "error_class":_http_status(exc)}
        except (RuntimeError,ValueError,TypeError) as exc:
            out[symbol]={"status":"ASSET_LOOKUP_INVALID",
                         "error_class":type(exc).__name__}
    return out


def fetch_exchange_registry(*, fetcher=http_bytes):
    headers=_headers()
    if headers is None:
        return {"status":"CREDENTIALS_NOT_CONFIGURED","codes":{}}
    try:
        raw=fetcher(EXCHANGE_ENDPOINT,headers,limit=MAX_META_BYTES)
        parsed=_typed_metadata_map(json.loads(raw))
        if not parsed or any(not code or len(code)>3 for code in parsed):
            raise RuntimeError("VENUE_METADATA_INVALID_CODES")
        return {"status":"EXCHANGE_REGISTRY_RETRIEVED",
                "codes":parsed,"metadata_sha256":sha256(raw).hexdigest()}
    except (HTTPError,URLError,TimeoutError) as exc:
        return {"status":"EXCHANGE_REGISTRY_UNAVAILABLE",
                "error_class":_http_status(exc),"codes":{}}
    except (RuntimeError,ValueError,TypeError) as exc:
        return {"status":"EXCHANGE_REGISTRY_INVALID",
                "error_class":type(exc).__name__,"codes":{}}


def classify_session_listing(symbol,session,canonical):
    """Known listing migrations invalidate current-master historical inference."""
    day=date.fromisoformat(session)
    if symbol=="PLTR" and day<date(2024,11,26) and canonical=="NASDAQ":
        return "HISTORIC_LISTING_TRANSFER_MISMATCH_HOLD"
    # 2024 PLTR migration is SEC-validated, but the rest of a live snapshot
    # is not a certified point-in-time historical master for prior days.
    return "CURRENT_MASTER_AS_OF_FETCH_ONLY_NOT_HISTORIC_CERTIFICATION"


def audit(independent, reference, universe, *, fetcher=http_bytes, stamp=None):
    if independent.get("version")!="daily20-independent-feed-diagnostics-v1":
        raise RuntimeError("INDEPENDENT_EVIDENCE_WRONG_VERSION")
    session=independent.get("session")
    if not isinstance(session,str):
        raise RuntimeError("VENUE_SESSION_ABSENT")
    date.fromisoformat(session)
    names=list(universe["core"]+universe["context"])
    if len(names)!=26 or "^VIX" not in names or len(set(names))!=26:
        raise RuntimeError("VENUE_UNIVERSE_INCOMPATIBLE")
    if reference.get("schema")!=QUOTES_VERSION or reference.get("session")!=session:
        raise RuntimeError("VENUE_QUOTE_REFERENCE_MISMATCH")
    existing=reference.get("quotes",[])
    if any(item.get("symbol") not in names for item in existing):
        raise RuntimeError("VENUE_REFERENCE_UNKNOWN_SYMBOL")
    # Preserve original Cboe-only VIX reference and provider-origin proof.
    selected_reference=[dict(item) for item in existing if item["symbol"]=="^VIX"]
    if len(selected_reference)>1:
        raise RuntimeError("DUPLICATED_VIX_REFERENCE")
    equities=[s for s in names if s!="^VIX"]
    source=independent.get("alpaca",{}).get("symbols",{})
    if set(source)!=set(equities):
        raise RuntimeError("VENUE_SIP_25_SYMBOL_COVERAGE_MISMATCH")
    acquired=fetch_assets(equities,fetcher=fetcher)
    registry=fetch_exchange_registry(fetcher=fetcher)
    collected_at=stamp or utc_time()
    rows=[]
    for symbol in equities:
        asset=acquired[symbol]
        auction=source[symbol]
        prior_quotes=auction.get("quotes",[])
        if not isinstance(prior_quotes,list):
            raise RuntimeError("VENUE_EXPECTED_QUOTE_LIST")
        if asset["status"]!="ASSET_MASTER_LIST_RETRIEVED":
            decision={"status":asset["status"],"canonical":None,
                      "venue_codes":[],"selected":None}
        elif registry["status"]!="EXCHANGE_REGISTRY_RETRIEVED":
            decision={"status":registry["status"],"canonical":canonical_exchange(asset["exchange"]),
                      "venue_codes":[],"selected":None}
        elif not asset["active"]:
            decision={"status":"ASSET_NOT_ACTIVE_IN_CURRENT_MASTER",
                      "canonical":canonical_exchange(asset["exchange"]),
                      "venue_codes":[],"selected":None}
        else:
            decision=resolve(asset["exchange"],registry["codes"],prior_quotes)
        historic=classify_session_listing(symbol,session,decision["canonical"])
        if historic=="HISTORIC_LISTING_TRANSFER_MISMATCH_HOLD":
            decision={**decision,"status":historic,"selected":None}
        selected=decision["selected"]
        if selected:
            selected_reference.append({
                "symbol":symbol,
                "quote_type":"REGULAR_CLOSE",
                "price":selected["price"],
                "adjustment":"RAW",
                "provider":"Alpaca",
                "feed":"SIP_MarketCenterOfficialClose_M",
                "observed_at_utc":selected["timestamp_utc"],
                "fetched_at_utc":collected_at,
                "exchange":selected["exchange"],
                "primary_listing_exchange_as_reported_by_alpaca":asset["exchange"],
                "listing_master_snapshot_sha256":asset["metadata_sha256"],
                "exchange_registry_sha256":registry["metadata_sha256"],
                "observed_timestamp_kind":"MARKET_CENTER_M_PRINT_NOT_CONSOLIDATED_CERTIFIED",
                "source_body_page_sha256":independent["alpaca"]["raw_response_sha256"],
                "independently_exchange_certified_at_16_00":False,
                "independent_historical_listing_certified":False,
            })
        rows.append({
            "symbol":symbol, "session":session,
            "asset_lookup_status":asset["status"],
            "asset_exchange":asset.get("exchange"),
            "asset_active":asset.get("active"),
            "asset_metadata_sha256":asset.get("metadata_sha256"),
            "primary_canonical":decision["canonical"],
            "exchange_registry_code":decision["venue_codes"],
            "exchange_registry_status":registry["status"],
            "market_centers_with_M_quote":sorted({q["exchange"] for q in prior_quotes}),
            "market_center_quote_count":len(prior_quotes),
            "primary_selection_status":decision["status"],
            "selected_primary_raw_M_price":selected["price"] if selected else None,
            "selected_primary_venue_code":selected["exchange"] if selected else None,
            "selected_primary_timestamp_utc":selected["timestamp_utc"] if selected else None,
            "listing_asof_evidence":historic,
            "session_primary_listing_certified":False,
            "primary_market_center_M_certified_as_consolidated_close":False,
            "direct_comparison_with_Yahoo_auto_adjust":False,
        })
    report={
        "version":VERSION,"session":session,"research_only":True,
        "production_writes":False,"live_execution":False,"strategy_promoted":False,
        "source_session_checked":True,
        "timestamp_utc":collected_at,
        "source_registry":registry,
        "primary_master_source":ASSET_ENDPOINT,
        "source_listing_metadata_is_current_not_historical":True,
        "primary_session_asof_independently_certified":False,
        "corporate_action_adjustment_factor_independently_certified":False,
        "raw_and_yahoo_adjusted_directly_comparable":False,
        "total_equities_etfs":25,"tested_assets":len(rows),
        "source_M_auction_25_coverage":sum(bool(source[s]["quotes"]) for s in equities),
        "asset_metadata_count":sum(a["status"]=="ASSET_MASTER_LIST_RETRIEVED" for a in acquired.values()),
        "primary_M_quote_research_selection_count":sum(bool(r["selected_primary_raw_M_price"])
                        for r in rows),
        "finality_verified":0,
        "selected_reference_count_including_cboe":len(selected_reference),
        "status":"PRIMARY_VENUE_RESEARCH_EVIDENCE_ONLY_FINALITY_HOLD",
        "rows":rows,
        "limitations":[
            "No primary-listing market history proof exists for all 25 dates; asset master is current at fetch, not session-point-in-time.",
            "A Market Center M condition is not by itself an independent consolidated closing price.",
            "Alpaca SIP auctions are raw prices and Yahoo model input is adjusted. No third-party adjustment factor comparison is performed.",
            "Close prices are retained without reconstructing trades, changing model features or upgrading research to LIVE.",
        ],
    }
    result={"schema":QUOTES_VERSION,"session":session,"research_only":True,
            "quotes":selected_reference}
    if report["tested_assets"]!=25 or report["finality_verified"]!=0:
        raise RuntimeError("VENUE_AUDIT_FALSE_FINISHED_STATUS")
    return report,result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--independent",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--config",default="research/kalman_daily20/universe.json")
    p.add_argument("--out-report",required=True)
    p.add_argument("--out-reference",required=True)
    a=p.parse_args()
    independent=json.loads(Path(a.independent).read_text())
    original=json.loads(Path(a.reference).read_text())
    report,selected=audit(independent,original,load_spec(a.config))
    write_json(a.out_report,report)
    write_json(a.out_reference,selected)
    print(json.dumps({"DAILY20_PRIMARY_LISTING_VENUE":{
        "session":report["session"],
        "asset_master_count":report["asset_metadata_count"],
        "M_quotes":report["source_M_auction_25_coverage"],
        "selected_research_only":report["primary_M_quote_research_selection_count"],
        "reference_count":report["selected_reference_count_including_cboe"],
        "finality_verified":0,
        "status":report["status"],
    }}))


if __name__=="__main__":
    main()
