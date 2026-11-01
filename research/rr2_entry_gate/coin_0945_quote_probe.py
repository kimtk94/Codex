#!/usr/bin/env python3
"""COIN 09:45 historical SIP NBBO-like top-of-book quote pilot; research-only.

Private original V_unweighted signal list and 15m bars required. Reconstructs
predeclared PRIOR_LOW_BUFFER_2R 4-session executed cohorts 2025 n=17 and 2026
n=7. Queries *preceding* quotes, never future snapshots for a supposed 09:45
fill. Raw SIP quotes may not share adjustment basis with adjusted=all SIP bars:
flag mismatches, never silently compare. No order/fill or licensed quote output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from coin_signal_replay import load_ledger, validate_entries
from coin_structure import build_sessions, geometry, simulate

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
URL = "https://data.alpaca.markets/v2/stocks/COIN/quotes"
COST = .003
# B pilot references original model-matched frozen 30bp 4-day path.
EXPECTED = {2025: 17, 2026: 7}
LOOKBACK_SECONDS = 5
MAX_STALENESS_MS = 1000
MAX_REQUEST_PAGES = 8


def timestamp(value):
    # Python accepts fractional seconds up to microseconds; sub-µs is irrelevant
    # to the prescribed 1000-ms quote staleness gate.
    x = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if x.tzinfo is None:
        raise ValueError("NAIVE_QUOTE_TIMESTAMP")
    return x.astimezone(UTC)


def select_pre_quote(quotes, decision_at, *, max_age_ms=MAX_STALENESS_MS):
    """Choose last quote no later than the decision; no future leakage."""
    if decision_at.tzinfo is None:
        raise ValueError("NAIVE_ENTRY_TIMESTAMP")
    cutoff = decision_at.astimezone(UTC)
    pre = []
    for q in quotes:
        t=timestamp(q["t"])
        if t<=cutoff:
            pre.append((t,q))
    if not pre:
        return {"status":"NO_PRE_ENTRY_QUOTE"}
    t,q=max(pre,key=lambda item:item[0])
    age=round((cutoff-t).total_seconds()*1000,3)
    if age<0:
        raise AssertionError("LOOKAHEAD")
    if age>max_age_ms:
        return {"status":"STALE_PRE_ENTRY_QUOTE"}
    try:
        bid,ask=float(q["bp"]),float(q["ap"])
        # Historical size units changed, so do NOT claim position capacity.
    except (KeyError,ValueError,TypeError):
        return {"status":"BAD_QUOTE_SCHEMA"}
    if not (math.isfinite(bid) and math.isfinite(ask)
            and bid>0 and ask>bid):
        return {"status":"CROSSED_ZERO_OR_INVALID_QUOTE"}
    if (ask-bid)/((ask+bid)/2)>.02:
        return {"status":"EXTREME_SPREAD_QUOTE"}
    return {"status":"QUOTE_PROXY_ELIGIBLE","bp":bid,"ap":ask,
            "quote_age_ms":age,
            "spread_bps":1e4*(ask-bid)/((ask+bid)/2),
            "exchange_bid":str(q.get("bx","?")),"exchange_ask":str(q.get("ax","?"))}


def fetch_quotes(start,end,key,secret,*,session=None):
    if not key or not secret: raise RuntimeError("MISSING_SIP_QUOTE_CREDENTIALS")
    payload=[]
    cursor=None
    seen=set()
    for _ in range(MAX_REQUEST_PAGES):
        q={"start":start.isoformat().replace("+00:00","Z"),
           "end":end.isoformat().replace("+00:00","Z"),
           "sort":"asc","feed":"sip","limit":10000}
        if cursor:q["page_token"]=cursor
        req=Request(URL+"?"+urlencode(q),method="GET",
                    headers={"APCA-API-KEY-ID":key,
                             "APCA-API-SECRET-KEY":secret,
                             "Accept":"application/json"})
        answer=None
        for attempt in range(5):
            try:
                with urlopen(req,timeout=35) as response:
                    answer=json.load(response)
                break
            except HTTPError as e:
                if e.code not in (429,500,502,503,504):
                    raise RuntimeError(f"SIP_QUOTE_HTTP_{e.code}") from None
                if attempt==4: raise RuntimeError(f"SIP_QUOTE_HTTP_{e.code}") from None
            except (URLError,TimeoutError):
                if attempt==4: raise RuntimeError("SIP_QUOTE_NETWORK_ERROR") from None
            time.sleep(min(2**attempt,8))
        if not isinstance(answer,dict) or not isinstance(answer.get("quotes"),list):
            raise RuntimeError("SIP_QUOTE_BAD_RESPONSE")
        payload.extend(answer["quotes"])
        next_cursor=answer.get("next_page_token")
        if not next_cursor:
            return payload
        if next_cursor in seen:
            raise RuntimeError("SIP_QUOTE_PAGE_TOKEN_LOOP")
        seen.add(next_cursor)
        cursor=next_cursor
    raise RuntimeError("SIP_QUOTE_PAGINATION_INCOMPLETE")


def selected_B(sessions,ledger,*,expected=EXPECTED):
    entries=validate_entries(ledger,sessions,expected={2025:80,2026:46})
    out={}
    for year in (2025,2026):
        cohort=[i for i,r in entries if int(r["entry_date"][:4])==year]
        chosen=[];last_exit=-1
        for i in cohort:
            entry=sessions[i]["bars"][1]["o"]
            g=geometry(entry,sessions[i]["bars"][0]["l"],
                       sessions[i-1]["low"],
                       max(s["high"] for s in sessions[i-20:i]),
                       "PRIOR_LOW_BUFFER_2R")
            if not g["pass"] or i+4>len(sessions) or i<=last_exit:
                continue
            tr=simulate(sessions,i,4,g["stop_pct"],g["target_pct"])
            chosen.append((i,g,tr));last_exit=tr["exit_index"]
        if len(chosen)!=expected[year]:
            raise ValueError(f"ORIGINAL_B_4DAY_COHORT_MISMATCH_{year}_{len(chosen)}")
        out[year]=chosen
    return out


def percentile(vals,q):
    if not vals:return None
    vals=sorted(vals)
    k=(len(vals)-1)*q;i=int(k)
    return round(vals[i]*(1-(k-i))+vals[min(i+1,len(vals)-1)]*(k-i),4)


def audit(sessions,ledger,key,secret,*,fetcher=fetch_quotes,original_sha=None):
    pairs=selected_B(sessions,ledger)
    years={}
    for year,group in pairs.items():
        counts=Counter();premiums=[];spreads=[];ages=[];old_rr=[];new_rr=[]
        entry_premiums_gt_zero=0
        cost_rr_breached=0
        quote_basis_outliers=0
        for i,g,tr in group:
            decision=datetime.combine(datetime.fromisoformat(
                sessions[i]["date"]).date(),
                datetime.min.time().replace(hour=9,minute=45),
                NY).astimezone(UTC)
            try:
                quotes=fetcher(decision-timedelta(seconds=LOOKBACK_SECONDS),
                               decision,key,secret)
            except RuntimeError as e:
                counts[str(e)]+=1
                continue
            q=select_pre_quote(quotes,decision)
            counts[q["status"]]+=1
            if q["status"]!="QUOTE_PROXY_ELIGIBLE":continue
            entry=tr["entry_price"]
            midpoint=(q["bp"]+q["ap"])/2
            # SIP quotes raw, 15m bar adjusted=all: large mismatch may be
            # corporate-action adjustment or aggregation/market-time drift.
            if abs(midpoint/entry-1)>.02:
                quote_basis_outliers+=1
                continue
            premium_bps=1e4*(q["ap"]/entry-1)
            entry_premiums_gt_zero+=int(premium_bps>0)
            premiums.append(premium_bps)
            spreads.append(q["spread_bps"])
            ages.append(q["quote_age_ms"])
            stop_level=entry*(1-g["stop_pct"])
            target_level=entry*(1+g["target_pct"])
            old=(g["target_pct"]-COST)/(g["stop_pct"]+COST)
            # Keep original absolute stop/target and substitute the historical
            # PRE-entry ask as a *hypothetical* marketable-buy price proxy.
            new=((target_level/q["ap"]-1-COST)/
                 (1-stop_level/q["ap"]+COST))
            old_rr.append(old);new_rr.append(new)
            cost_rr_breached+=int(new<2-1e-9)
        usable=len(premiums)
        years[str(year)]={
            "original_B_4session_executed":len(group),
            "quotes_usable_for_bar_alignment":usable,
            "quote_status_counts":dict(counts),
            "raw_quote_adjusted_bar_basis_outlier_count":quote_basis_outliers,
            "midpoint_open_tolerance_fraction":.02,
            "valid_quote_coverage":round(usable/len(group),6),
            "pre_entry_ask_minus_15min_open_bps":{
                "p10":percentile(premiums,.1),"median":percentile(premiums,.5),
                "p90":percentile(premiums,.9),
            },
            "quoted_bid_ask_spread_bps":{
                "median":percentile(spreads,.5),
                "p90":percentile(spreads,.9),
            },
            "snapshot_age_ms_median":percentile(ages,.5),
            "positive_ask_premium_count":entry_premiums_gt_zero,
            "planned_net_RR2_breached_if_original_absolute_target_and_stop_unchanged":cost_rr_breached,
            "quote_proxy_rr_original_median":percentile(old_rr,.5),
            "quote_proxy_rr_substituted_median":percentile(new_rr,.5),
            "no_full_trade_replay_from_entry_snapshot":True,
        }
    return {
        "schema":"coin-pit-original-model-0945-sip-quote-entry-proxy-v1",
        "status":"QUOTE_PROXY_DIAGNOSTIC_ONLY_NOT_EXECUTION_VALIDATION",
        "live":"HOLD","source_ledger_sha256":original_sha,
        "original_signal_year_counts":{"2025":80,"2026":46},
        "sample":"PRIOR_LOW_BUFFER_2R_NONOVERLAP_4SESSIONS_2025_17_2026_7",
        "entry_snapshot":"LATEST_PRE_0945_QUOTE_WITHIN_1000MS_NOT_FUTURE",
        "source":"ALPACA_SIP_RAW_QUOTES_VS_ADJUSTMENT_ALL_BARS",
        "quotes_are_not_executable_orders":True,
        "quote_size_unit_changes_across_history_not_used":True,
        "cost_double_counting_risk":"30bp baseline ALREADY includes assumed 5bp-per-side slippage; ask premium is NOT safely additive to 30bp",
        "quote_basis_sensitivity":"2percent midpoint/open threshold; flagged observations not treated as identical basis",
        "exit_intrabar_quote_or_order_fill_verified":False,
        "historical_research_not_unseen_oos":True,
        "years":years,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--private-ledger",required=True,type=Path)
    p.add_argument("--private-bars",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    ledger,h=load_ledger(a.private_ledger)
    import pandas as pd
    barframe=pd.read_parquet(a.private_bars)
    coin=barframe.loc[barframe.market.eq("COIN")]
    bars=[{"t":str(x.candle_time_utc),"o":float(x.open),"h":float(x.high),
           "l":float(x.low),"c":float(x.close)} for x in coin.itertuples(index=False)]
    sessions,q=build_sessions(bars,start="2024-01-01",end="2026-10-30")
    if q["incomplete_sessions"] or q["complete_sessions"]!=711:
        raise ValueError("SIP_SOURCE_711_PARITY_FAIL")
    data=audit(sessions,ledger,
               os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID",""),
               os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY",""),
               original_sha=h)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps({"status":data["status"],"live":"HOLD",
          "years":{y:{"n":z["original_B_4session_executed"],
                       "valid_quote":z["quotes_usable_for_bar_alignment"]}
                   for y,z in data["years"].items()}}))

if __name__=="__main__":main()
