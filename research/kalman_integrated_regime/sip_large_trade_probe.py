#!/usr/bin/env python3
"""Alpaca SIP historical individual-trade access probe (read-only).

Research-only, never writes any live trading state. Query one completed
one-minute interval per symbol. Public artifact is aggregate counts only,
NEVER raw licensed SIP prints or credentials.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

import requests


URL = "https://data.alpaca.markets/v2/stocks/{symbol}/trades"
SYMBOLS = ("QQQ", "QLD")
START = "2026-10-29T15:00:00Z"
END = "2026-10-29T15:00:59.999999Z"
AMOUNTS = (100_000, 1_000_000)


def summarize(trades):
    """Do not equate a large print with an institutional buy or sell."""
    valid = [t for t in trades if t.get("u") not in ("canceled", "incorrect")]
    amounts = []
    shares = []
    for t in valid:
        price, qty = float(t["p"]), int(t["s"])
        if price <= 0 or qty <= 0:
            raise ValueError("INVALID_TRADE_PRICE_SIZE")
        amounts.append(price * qty)
        shares.append(qty)
    amounts.sort()
    shares.sort()
    by_exchange = Counter(str(t.get("x", "?")) for t in valid)
    conditions = Counter(flag for t in valid for flag in t.get("c", []))
    def quantile(values, q):
        return round(values[min(len(values)-1, int(q*(len(values)-1)))], 2) if values else None
    return {
        "trades_valid": len(valid),
        "trades_canceled_or_incorrect": len(trades) - len(valid),
        "shares_total": sum(shares),
        "notional_usd_approx": round(sum(amounts), 2),
        "trade_notional_p50_usd": quantile(amounts, .5),
        "trade_notional_p95_usd": quantile(amounts, .95),
        "trade_notional_p99_usd": quantile(amounts, .99),
        "trade_notional_max_usd": quantile(amounts, 1.),
        "prints_over_100k": sum(v >= AMOUNTS[0] for v in amounts),
        "prints_over_1m": sum(v >= AMOUNTS[1] for v in amounts),
        "shares_p99": quantile(shares, .99),
        "exchanges": dict(by_exchange),
        "condition_counts": dict(conditions),
        "buy_sell_direction": "NOT_PROVIDED_BY_TRADE_TAPE",
        "note": "SIP print >= threshold does not establish order-owner identity, hidden size, aggressor or institutional activity."
    }


def download_symbol(session, symbol, key, secret, max_pages):
    tokens = set()
    token = None
    trades = []
    pages = 0
    for _ in range(max_pages):
        q = {"start":START, "end":END, "feed":"sip", "sort":"asc",
             "limit":10000}
        if token:
            q["page_token"] = token
        headers = {"APCA-API-KEY-ID":key, "APCA-API-SECRET-KEY":secret}
        response = None
        for attempt in range(3):
            try:
                response = session.get(URL.format(symbol=symbol), params=q, headers=headers, timeout=35)
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError("ALPACA_TRANSPORT_FAILURE") from None
                time.sleep(2*(attempt+1))
                continue
            if response.status_code in (429,500,502,503,504) and attempt < 2:
                time.sleep(2*(attempt+1))
                continue
            break
        if response is None or response.status_code != 200:
            raise RuntimeError("ALPACA_HTTP_"+str(getattr(response,"status_code","UNKNOWN")))
        try:
            obj=response.json()
        except ValueError:
            raise RuntimeError("ALPACA_BAD_JSON") from None
        if not isinstance(obj,dict) or not isinstance(obj.get("trades"),list):
            raise RuntimeError("ALPACA_BAD_TRADES_SCHEMA")
        for t in obj["trades"]:
            if not all(k in t for k in ("p","s","t","x","c")):
                raise RuntimeError("ALPACA_MISSING_REQUIRED_FIELD")
        trades.extend(obj["trades"])
        pages += 1
        token = obj.get("next_page_token")
        if token is None:
            return summarize(trades) | {"pages":pages,"fully_paginated":True}
        if token in tokens:
            raise RuntimeError("ALPACA_REPEAT_PAGE_TOKEN")
        tokens.add(token)
    # An incomplete sample cannot be presented as a distribution of the full interval.
    return {"status":"CAPPED_INCOMPLETE","pages":pages,
            "trades_fetched":len(trades),"fully_paginated":False}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=False,default="data_probe_summary.json")
    ap.add_argument("--max-pages",type=int,default=15)
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        s=summarize([{"p":500.0,"s":200,"x":"Q","c":["@"]},
                     {"p":500.0,"s":2000,"x":"D","c":["@"],"u":"corrected"},
                     {"p":500.0,"s":10,"x":"Q","c":["@"],"u":"canceled"}])
        assert s["prints_over_100k"]==2
        assert s["prints_over_1m"]==1
        assert s["trades_valid"]==2
        assert s["trades_canceled_or_incorrect"]==1
        print("SIP_TRADE_PROBE_SELFTEST_OK")
        return
    if args.max_pages < 1 or args.max_pages > 50:
        raise SystemExit("MAX_PAGES_OUT_OF_BOUNDS")
    key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
    secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    result={"schema":"alpaca-sip-large-trade-aggregate-probe-v1",
            "status":"STARTED",
            "symbols":list(SYMBOLS),
            "window_utc":{"start":START,"end":END},
            "market_data_feed":"sip",
            "read_only":True,"no_live_changes":True,
            "not_raw_trade_feed":True,"size_adjustment":"RAW_PRINT_NOTIONAL",
            "results":{}}
    if not key or not secret:
        result.update(status="BLOCKED",reason="MISSING_CI_SECRET")
    else:
        with requests.Session() as session:
            for symbol in SYMBOLS:
                try:
                    result["results"][symbol]=download_symbol(session,symbol,key,secret,args.max_pages)
                except RuntimeError as e:
                    result["results"][symbol]={"status":"BLOCKED", "reason":str(e)}
        result["status"]="PASS" if all(
            r.get("fully_paginated") and r.get("trades_valid",0)>0
            for r in result["results"].values()) else "HOLD_INCOMPLETE_OR_UNAVAILABLE"
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("SIP_TRADE_PROBE "+json.dumps(result,ensure_ascii=False))
    if result["status"] != "PASS":
        sys.exit(2)


if __name__=="__main__":
    main()
