#!/usr/bin/env python3
"""Classify *aggressive-side estimates* by preceding SIP top-of-book quote.

Each printed trade has a buyer and seller: there is no literal buy-vs-sell
volume in the consolidated prints. This probe estimates which party crossed
the spread and always retains UNKNOWN, non-regular and ambiguous observations.

A historical 10-second time window is fetched for QLD / QQQ, with a 2-second
pre-window quote lookback. Never upload licensed raw trades/quotes.
"""
from __future__ import annotations
from bisect import bisect_left
from collections import Counter
import argparse
import json
import os
from pathlib import Path
import time

import pandas as pd
import requests

BASE = "https://data.alpaca.markets/v2/stocks"
SYMBOLS = ("QQQ", "QLD")
TRADE_START = "2026-10-29T15:00:00Z"
TRADE_END = "2026-10-29T15:00:09.999999999Z"
QUOTE_START = "2026-10-29T14:59:58Z"
QUOTE_END = TRADE_END


def timestamp(s):
    return pd.Timestamp(s).tz_convert("UTC") if pd.Timestamp(s).tzinfo else pd.Timestamp(s,tz="UTC")


def fetch(session, symbol, kind, start, end, key, secret, max_pages):
    records=[]
    tokens=set()
    token=None
    for page in range(max_pages):
        q={"start":start,"end":end,"feed":"sip","sort":"asc","limit":10000}
        if token:
            q["page_token"]=token
        response=None
        for attempt in range(3):
            try:
                response=session.get(
                    f"{BASE}/{symbol}/{kind}",params=q,
                    headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret},
                    timeout=35)
            except requests.RequestException:
                if attempt==2:
                    raise RuntimeError("NETWORK_FAILURE") from None
                time.sleep(2*(attempt+1))
                continue
            if response.status_code in (429,500,502,503,504) and attempt<2:
                time.sleep(2*(attempt+1))
                continue
            break
        if response is None or response.status_code != 200:
            raise RuntimeError(kind+"_HTTP_"+str(getattr(response,"status_code","UNKNOWN")))
        try:
            payload=response.json()
        except ValueError:
            raise RuntimeError(kind+"_INVALID_JSON") from None
        if not isinstance(payload,dict) or not isinstance(payload.get(kind),list):
            raise RuntimeError(kind+"_INVALID_SCHEMA")
        records.extend(payload[kind])
        token=payload.get("next_page_token")
        if token is None:
            return records,page+1
        if token in tokens:
            raise RuntimeError(kind+"_DUPLICATE_PAGE_TOKEN")
        tokens.add(token)
    raise RuntimeError(kind+"_PAGE_CAP_UNRELIABLE")


def classify(trades, quotes, stale_ms=1000):
    quotes=sorted(quotes,key=lambda q:timestamp(q["t"]))
    quote_times=[timestamp(q["t"]) for q in quotes]
    outcomes=Counter()
    total_shares=Counter()
    total_notional=Counter()
    large_shares=Counter()
    large_count=Counter()
    unknown_reason=Counter()
    condition_counts=Counter()
    good_quote_count=0
    # For corrected prints and special conditions, the classification is
    # EXPLORATORY ONLY, not official market volume.
    for t in sorted(trades,key=lambda t:timestamp(t["t"])):
        px=float(t["p"])
        qty=int(t["s"])
        if px<=0 or qty<=0:
            raise ValueError("BAD_TRADE_PRINT")
        ts=timestamp(t["t"])
        amount=px*qty
        for c in t.get("c",[]):
            condition_counts[str(c)]+=1
        side="UNKNOWN"
        reason="NO_PRIOR_QUOTE"
        i=bisect_left(quote_times,ts)-1 # strictly earlier quote; no same-time lookahead
        if i>=0:
            q=quotes[i]
            bp,ap=float(q["bp"]),float(q["ap"])
            age=float((ts-quote_times[i]).total_seconds()*1000)
            if age>stale_ms:
                reason="STALE_QUOTE"
            elif bp<=0 or ap<=0 or bp>=ap:
                reason="BAD_SPREAD"
            elif bp<=px<=ap:
                good_quote_count+=1
                midpoint=(bp+ap)/2
                if px>=ap-1e-9:
                    side="BUY_INITIATED_ESTIMATE"
                    reason="AT_ASK"
                elif px<=bp+1e-9:
                    side="SELL_INITIATED_ESTIMATE"
                    reason="AT_BID"
                elif px>midpoint+1e-9:
                    side="BUY_INITIATED_ESTIMATE_LOW_CONFIDENCE"
                    reason="INSIDE_ABOVE_MID"
                elif px<midpoint-1e-9:
                    side="SELL_INITIATED_ESTIMATE_LOW_CONFIDENCE"
                    reason="INSIDE_BELOW_MID"
                else:
                    reason="AT_MIDPOINT"
            else:
                reason="TRADE_OUTSIDE_SPREAD"
        outcomes[side]+=1
        total_shares[side]+=qty
        total_notional[side]+=amount
        if side=="UNKNOWN":
            unknown_reason[reason]+=1
        if amount>=100_000:
            large_count[side]+=1
            large_shares[side]+=qty
    if sum(outcomes.values())!=len(trades):
        raise AssertionError("PRINT_COUNT_DISAGREEMENT")
    if sum(total_shares.values())!=sum(int(t["s"]) for t in trades):
        raise AssertionError("SHARE_RECONCILIATION_FAILED")
    if len(trades)==0 or len(quotes)==0:
        raise RuntimeError("EMPTY_TRADE_OR_QUOTE_TAPE")
    highbuy=total_shares["BUY_INITIATED_ESTIMATE"]
    highsell=total_shares["SELL_INITIATED_ESTIMATE"]
    denominator=highbuy+highsell
    return {
        "prints_total":len(trades),
        "quotes_total":len(quotes),
        "prints_with_valid_preceding_spread":good_quote_count,
        "counts_by_class":dict(outcomes),
        "shares_by_class":dict(total_shares),
        "notional_usd_by_class":{k:round(v,2) for k,v in total_notional.items()},
        "prints_over_100k_by_class":dict(large_count),
        "shares_over_100k_by_class":dict(large_shares),
        "unknown_reasons":dict(unknown_reason),
        "raw_condition_counts":dict(condition_counts),
        "high_confidence_aggressor_share_imbalance":
            round((highbuy-highsell)/denominator,6) if denominator else None,
        "high_confidence_classified_share_pct":
            round(100*denominator/sum(total_shares.values()),4),
        "classification_basis":"PRECEDING_QUOTE_STRICTLY_BEFORE_PRINT_TIMESTAMP",
        "max_quote_staleness_ms":stale_ms,
        "not_an_institutional_side_or_proven_buy_sell_order_flow":True,
        "raw_trade_conditions_not_filtered":True,
        "correction_deduplication_not_validated":True,
        "public_summary_only":True,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="sip_signed_volume_probe.json")
    p.add_argument("--max-pages",type=int,default=15)
    p.add_argument("--stale-ms",type=int,default=1000)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:
        q=[{"t":"2026-10-29T15:00:00.000000100Z","bp":99.0,"ap":101.0}]
        t=[{"t":"2026-10-29T15:00:00.000000200Z","p":101.0,"s":100,"c":["@"]},
           {"t":"2026-10-29T15:00:00.000000300Z","p":99.0,"s":50,"c":["@"]},
           {"t":"2026-10-29T15:00:00.000000400Z","p":100.0,"s":20,"c":["@"]},
           {"t":"2026-10-29T15:00:00.000000050Z","p":100.0,"s":10,"c":["@"]}]
        x=classify(t,q,1000)
        assert x["shares_by_class"]["BUY_INITIATED_ESTIMATE"]==100
        assert x["shares_by_class"]["SELL_INITIATED_ESTIMATE"]==50
        assert x["shares_by_class"]["UNKNOWN"]==30
        assert x["counts_by_class"]["UNKNOWN"]==2
        assert x["high_confidence_aggressor_share_imbalance"]==round(50/150,6)
        print("QUOTE_AGGRESSOR_PROBE_SELFTEST_OK")
        return
    if not 1<=a.max_pages<=40 or not 100<=a.stale_ms<=2000:
        raise SystemExit("BAD_BOUND")
    key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
    secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    result={"schema":"qld-qqq-sip-preceding-quote-aggressor-estimate-v1",
            "status":"RUNNING","window_utc":{"trades":[TRADE_START,TRADE_END],
                    "quotes":[QUOTE_START,QUOTE_END]},
            "feed":"sip","read_only":True,
            "trade_side_is_inferred_not_directly_observed":True,
            "no_live_changes":True,"results":{}}
    if not key or not secret:
        result.update(status="HOLD",reason="MISSING_SIP_CREDENTIALS")
    else:
        with requests.Session() as sess:
            for symbol in SYMBOLS:
                try:
                    trades,tp=fetch(sess,symbol,"trades",TRADE_START,TRADE_END,key,secret,a.max_pages)
                    quotes,qp=fetch(sess,symbol,"quotes",QUOTE_START,QUOTE_END,key,secret,a.max_pages)
                    stats=classify(trades,quotes,a.stale_ms)
                    result["results"][symbol]=stats | {
                        "trade_pages":tp,"quote_pages":qp,"status":"EXPLORATORY_ESTIMATE"}
                except (RuntimeError,ValueError) as exc:
                    result["results"][symbol]={"status":"HOLD","reason":str(exc)}
        result["status"]="PASS_EXPLORATORY_PROBE" if all(
            a.get("status")=="EXPLORATORY_ESTIMATE"
            for a in result["results"].values()) else "HOLD_PARTIAL_OR_UNAVAILABLE"
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("SIP_QUOTE_SIGNED_VOLUME_PROBE "+json.dumps(result,ensure_ascii=False),flush=True)
    if result["status"]!="PASS_EXPLORATORY_PROBE":
        raise SystemExit(2)


if __name__=="__main__":
    main()
