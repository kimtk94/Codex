#!/usr/bin/env python3
"""Retrospective quote headroom and private targeted SIP collection.

Public CI only computes aggregate diagnostics from the pinned daily archive.
Private collection is an explicit operator action, GET-only and fail closed.
No adjusted-to-raw price conversion without independent evidence, no fill claim,
no new signals, no orders, no credentials or licensed rows in public artifacts.
"""
import argparse
from collections import defaultdict, Counter
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd
import exchange_calendars as xc

from challenger_execution_audit import replay, summary, NAMES, CAPITAL
from challenger_forward_producer import archive_frames, pinned
from challenger_prequential import load_protocol, require, sha

SHOCKS=(0,5,10,20,50)
ENDPOINT="https://data.alpaca.markets/v2/stocks/"
CUTOFF="2026-11-23"


def bounds(t,bp):
    op,stop,target=t["open"],t["stop"],t["target"]
    require(0<stop<op<target and bp in (30,50),"QUOTE_LEVELS")
    c=bp/10000
    h=c/2
    low=max(stop/.995,target/1.08)
    high=min((target+2*stop)/(3*(1+c)),
             (target+2*stop)*(1-h)/(3*(1+h)),stop/.97)
    require(low<=op+1e-9 and high>=op-1e-9,"QUOTE_ORIGINAL_GATE")
    return low,high


def shock_replay(entries,bars,n,bp,shock):
    h=bp/20000
    cash=CAPITAL
    held=[]
    eq=[]
    count=0
    byday=defaultdict(list)
    for t in entries:
        byday[t["entry"]].append(t)
    for i in range(n):
        opening=cash+sum(x["proceeds"] if x["closed"] else
                          x["qty"]*bars[x["symbol"]][i,0] for x in held)
        for t in byday[i]:
            ask=t["open"]*(1+shock/10000)
            low,high=bounds(t,bp)
            if not low-1e-9<=ask<=high+1e-9:
                continue
            require(len(held)<5 and not any(x["symbol"]==t["symbol"] for x in held),
                    "QUOTE_CAPACITY")
            spend=min(cash,.2*opening)
            if spend<=1e-7:
                continue
            cash-=spend
            held.append(dict(t,qty=spend/(ask*(1+h)),closed=False,proceeds=0.))
            count+=1
        for x in held:
            if x["exit"]==i:
                require(not x["closed"],"QUOTE_EXIT_TWICE")
                x["proceeds"]=x["qty"]*x["exit_price"]*(1-h)
                x["closed"]=True
            if x["due"]==i:
                require(x["closed"],"QUOTE_DUE_NOT_CLOSED")
                cash+=x["proceeds"]
        held=[x for x in held if x["due"]>i]
        val=cash+sum(x["proceeds"] if x["closed"] else
                     x["qty"]*bars[x["symbol"]][i,3] for x in held)
        require(cash>=-1e-7 and val>0,"QUOTE_CASH")
        eq.append(val)
    require(not held,"QUOTE_UNSETTLED")
    return np.asarray(eq),dict(summary(eq),trades=count)


def ranges(days,dates,grids):
    index={d:i for i,d in enumerate(dates)}
    bysym=defaultdict(list)
    for s,d in sorted(days):
        bysym[s].append(index[d])
    rows=[]
    for s,ks in bysym.items():
        groups=[]
        for k in ks:
            if not groups or k!=groups[-1][-1]+1:
                groups.append([k])
            else:
                groups[-1].append(k)
        for g in groups:
            ds=[dates[k] for k in g]
            rows.append(dict(symbol=s,sessions=ds,
                start_utc=grids[ds[0]][0].isoformat(),
                end_utc=(grids[ds[-1]][-1]+pd.Timedelta(minutes=15)).isoformat(),
                expected_regular_15m=sum(len(grids[d]) for d in ds)))
    return rows


def analyze(p,frames,last,ref):
    dates,grids,entries,curves,bars=replay(p,frames,last)
    scenarios={}
    windows=set()
    for name in NAMES:
        bp=int(name.split("_")[1])
        e=entries[name]
        head=np.asarray([(bounds(t,bp)[1]/t["open"]-1)*10000 for t in e])
        checks={}
        for shock in SHOCKS:
            eq,res=shock_replay(e,bars,len(dates),bp,shock)
            if shock==0:
                require(np.allclose(eq,curves[name],rtol=0,atol=1e-7)
                        and res["trades"]==ref["scenarios"][name]["trades"]
                        and abs(res["total_return"]-ref["scenarios"][name]["total_return"])<1e-10,
                        "QUOTE_REPLAY_PARITY")
            checks[str(shock)]=res
        scenarios[name]=dict(trades=len(e),headroom_bp=dict(zip(
            ["min","p05","p25","median","p75","p95","max"],
            map(float,np.quantile(head,[0,.05,.25,.5,.75,.95,1])))),
            hypothetical_adverse_ask=checks)
        windows.update((t["symbol"],t["entry"],t["due"]) for t in e)
    days={(s,dates[i]) for s,e,d in windows for i in range(e,d+1)}
    r=ranges(days,dates,grids)
    require(len(windows)==193 and len(days)==769 and len(r)==142 and
            sum(x["expected_regular_15m"] for x in r)==19946,"QUOTE_PLAN_PARITY")
    return dict(version="kalman-challenger-quote-headroom-v1",research_only=True,
        approved_live=False,forward_signals_created=0,source_finality_certified=False,
        real_quotes_measured=0,actual_quote_fills_verified=False,
        status="RETROSPECTIVE_RESEARCH_HOLD",sessions=len(dates),scenarios=scenarios,
        request_counts=dict(full_windows=len(windows),full_symbol_days=len(days),
            full_bar_ranges=len(r),full_expected_regular_bars=19946,entry_quote_requests=193),
        limitations=["Entry-only hypothetical adverse ask on aligned basis; retain baseline costs and fixed exits.",
            "Reject original admitted trades, never replace with alternatives. Not a live signal or new optimized model.",
            "Full-sample historical replay, no actual quotes or independently verified corporate-action factors."])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):
        return None


def get_pages(symbol,kind,start,end,adjustment=None,opener=None):
    require(re.fullmatch("[A-Z]{1,5}",symbol) is not None and kind in ("bars","quotes"),
            "SIP_SYMBOL_KIND")
    key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
    secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    require(bool(key and secret),"SIP_CREDENTIALS_REQUIRED")
    q=dict(start=start,end=end,feed="sip",limit=10000,sort="asc",asof="-",currency="USD")
    if kind=="bars":
        require(adjustment in ("raw","all"),"SIP_ADJUSTMENT")
        q.update(timeframe="15Min",adjustment=adjustment)
    opener=opener or build_opener(NoRedirect())
    rows=[]
    seen=set()
    for _ in range(32):
        req=Request(ENDPOINT+symbol+"/"+kind+"?"+urlencode(q),
                    headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                             "Accept":"application/json"},method="GET")
        for attempt in range(4):
            try:
                with opener.open(req,timeout=35) as res:
                    payload=json.loads(res.read(32*1024*1024+1))
                break
            except HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt==3:
                    raise RuntimeError("SIP_HTTP_"+str(exc.code)) from None
            except (URLError,TimeoutError):
                if attempt==3:
                    raise RuntimeError("SIP_NETWORK_FAILED") from None
            time.sleep(min(2**attempt,6))
        require(payload.get("symbol")==symbol and isinstance(payload.get(kind),list),
                "SIP_RESPONSE_IDENTITY")
        rows.extend(payload[kind])
        token=payload.get("next_page_token")
        if not token:
            return rows
        require(bool(payload[kind]) and token not in seen,"SIP_PAGINATION")
        seen.add(token)
        q["page_token"]=token
    raise RuntimeError("SIP_PAGE_LIMIT")


def quote_quality(rows,start,decision,session):
    start,decision=pd.Timestamp(start),pd.Timestamp(decision)
    require(decision-start==pd.Timedelta(seconds=1),"SIP_QUOTE_DECISION_WINDOW")
    eligible=[(pd.Timestamp(x["t"]),x) for x in rows if start<=pd.Timestamp(x["t"])<decision]
    if not eligible:
        return dict(status="NO_STRICT_PRIOR_REGULAR_QUOTE")
    latest=max(t for t,_ in eligible)
    same=[x for t,x in eligible if t==latest]
    if any(x!=same[0] for x in same):
        return dict(status="AMBIGUOUS_LATEST_QUOTE")
    x=same[0]
    bp,ap,bs,az=x["bp"],x["ap"],x["bs"],x["as"]
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and
               math.isfinite(v) and v>0 for v in (bp,ap,bs,az)) or ap<=bp or x.get("z") not in ("A","B","C"):
        return dict(status="INVALID_LATEST_QUOTE")
    return dict(status="RAW_QUOTE_OBSERVED_NOT_EXECUTION",
                age_ms=float((decision-latest)/pd.Timedelta(milliseconds=1)),
                spread_bp=10000*(ap-bp)/((ap+bp)/2),raw_bid=bp,raw_ask=ap,
                bid_size_reported=bs,ask_size_reported=az,
                size_unit="ROUND_LOTS" if session<"2025-11-03" else "SHARES",
                condition_flags=x.get("c"),condition_certified=False,
                quote_basis_verified=False,actual_fill_verified=False)


def validate_plan(plan,p):
    require(plan["version"]=="kalman-challenger-sip-request-plan-v1" and
            plan["research_only"] is True and plan["approved_live"] is False and
            plan["source_finality_certified"] is False and plan["forward_signals_created"]==0,
            "SIP_PLAN_SCOPE")
    require(plan["source_data_sha256"]=="6b5cec11a98fd160496d476ff7f773a3be8ecdaf49867cadadef9d20da6d36cf"
            and plan["source_research_sha256"]=="c6e711b7db3f91d5081947f95b320fe3cbbddfeb671df97edf9a24a4ff5f2d6f",
            "SIP_SOURCE_PIN")
    cal=xc.get_calendar("XNYS")
    sessions=cal.sessions_in_range("2024-01-02",CUTOFF)
    dates=[str(s.date()) for s in sessions]
    idx={s:i for i,s in enumerate(dates)}
    grids={d:pd.date_range(cal.session_open(s),cal.session_close(s),
                          freq="15min",inclusive="left") for d,s in zip(dates,sessions)}
    windows=plan["windows"]
    require(len(windows)==len({(x["symbol"],x["signal"]) for x in windows})==193,
            "SIP_WINDOWS")
    for x in windows:
        k=idx[x["signal"]]
        require(x["symbol"] in p["universe"] and x["sessions"]==dates[k+1:k+5]
                and len(x["sessions"])==4 and x["entry"]==x["sessions"][0]
                and x["fourth_session"]==x["sessions"][-1]
                and type(x["existing_15m_complete"]) is bool,"SIP_WINDOW_CALENDAR")
    all_days={(x["symbol"],d) for x in windows for d in x["sessions"]}
    missing={(x["symbol"],d) for x in windows if not x["existing_15m_complete"] for d in x["sessions"]}
    require(len(all_days)==769 and len(missing)==745 and
            sum(x["existing_15m_complete"] for x in windows)==6,"SIP_SCOPE_COUNTS")
    for key,days in (("full_bar_requests",all_days),("missing_bar_requests",missing)):
        require(plan[key]==ranges(days,dates,grids),"SIP_REQUEST_GRID")
    expected=[dict(symbol=x["symbol"],session=x["entry"],
            start_utc=grids[x["entry"]][0].isoformat(),
            decision_utc=(grids[x["entry"]][0]+pd.Timedelta(seconds=1)).isoformat())
        for x in sorted(windows,key=lambda x:(x["symbol"],x["signal"]))]
    require(expected==plan["quote_requests"] and len(expected)==193,"SIP_QUOTE_REQUEST_GRID")
    return grids


def collect(plan,p,out,scope):
    require(not os.getenv("GITHUB_ACTIONS"),"SIP_PRIVATE_HOST_ONLY")
    require(bool((os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")) and
                 (os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY"))),
            "SIP_CREDENTIALS_REQUIRED")
    grids=validate_plan(plan,p)
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    counts=Counter()
    # All raw responses and individual results remain local, never public.
    requests=plan["missing_bar_requests" if scope=="missing" else "full_bar_requests"]
    for n,r in enumerate(requests):
        expected={t for d in r["sessions"] for t in grids[d]}
        for adj in ("raw","all"):
            rows=get_pages(r["symbol"],"bars",r["start_utc"],r["end_utc"],adj)
            selected={}
            for x in rows:
                t=pd.Timestamp(x["t"])
                if t not in expected:
                    continue
                require(t not in selected,"SIP_DUPLICATE_RTH_BAR")
                o,h,l,c=(x[k] for k in ("o","h","l","c"))
                require(all(math.isfinite(v) and v>0 for v in (o,h,l,c)) and
                        l<=min(o,c)<=max(o,c)<=h,"SIP_INVALID_OHLC")
                selected[t]=x
            counts[adj+"_expected"]+=len(expected)
            counts[adj+"_observed"]+=len(selected)
            (out/f"bars_{n:03d}_{adj}.json").write_text(json.dumps(
                dict(request=r,adjustment=adj,bars=list(selected.values()),
                     missing=[t.isoformat() for t in sorted(expected-set(selected))]),
                allow_nan=False))
    for n,r in enumerate(plan["quote_requests"]):
        rows=get_pages(r["symbol"],"quotes",r["start_utc"],r["decision_utc"])
        q=quote_quality(rows,r["start_utc"],r["decision_utc"],r["session"])
        counts[q["status"]]+=1
        (out/f"quote_{n:03d}.json").write_text(json.dumps(
            dict(request=r,quotes=rows,quality=q),allow_nan=False))
    report=dict(status="PRIVATE_SIP_COLLECTION_NOT_EXECUTION",research_only=True,
                approved_live=False,source_finality_certified=False,forward_signals_created=0,
                actual_quote_fills_verified=False,quote_basis_verified=False,
                scope=scope,counts=dict(counts),raw_rows_private=True)
    (out/"aggregate.json").write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report))


def self_test():
    t=dict(open=100.,stop=98.,target=106.)
    low,high=bounds(t,30)
    require(low<=100<=high and high<101,"QUOTE_BOUNDS_TEST")
    a="2026-11-24T14:30:00Z";b="2026-11-24T14:30:01Z"
    q=dict(t="2026-11-24T14:30:00.500000000Z",bp=99.9,ap=100.,bs=1,
           **{"as":1},z="C",c=["R"])
    q2=dict(q,t=b,ap=101.)
    require(quote_quality([q,q2],a,b,"2026-11-24")["raw_ask"]==100.,
            "QUOTE_NO_EQUAL_TIME_LOOKAHEAD")
    require(quote_quality([q2],a,b,"2026-11-24")["status"]=="NO_STRICT_PRIOR_REGULAR_QUOTE",
            "QUOTE_MISSING_TEST")
    require(quote_quality([q,dict(q,ap=100.1)],a,b,"2026-11-24")["status"]=="AMBIGUOUS_LATEST_QUOTE",
            "QUOTE_AMBIGUOUS_TEST")
    require(quote_quality([q],a,b,"2025-11-02")["size_unit"]=="ROUND_LOTS",
            "QUOTE_SIZE_UNIT_TEST")
    require(quote_quality([dict(q,ap=0)],a,b,"2026-11-24")["status"]=="INVALID_LATEST_QUOTE",
            "QUOTE_INVALID_TEST")
    print("CHALLENGER_QUOTE_AUDIT_SYNTHETIC_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    a.add_argument("--private-collect",action="store_true")
    a.add_argument("--scope",choices=("missing","full"),default="missing")
    for k in ("data","data-sha256","research","research-sha256","reference","out","plan","plan-sha256"):
        a.add_argument("--"+k)
    x=a.parse_args()
    if x.self_test:
        self_test()
        return
    p,h=load_protocol()
    if x.private_collect:
        require(bool(x.plan and x.plan_sha256 and x.out),"SIP_PRIVATE_ARGUMENTS")
        plan=json.loads(pinned(x.plan,x.plan_sha256))
        collect(plan,p,x.out,x.scope)
        return
    require(all([x.data,x.data_sha256,x.research,x.research_sha256,x.reference,x.out]),
            "QUOTE_INPUTS")
    last,frames=archive_frames(p,pinned(x.data,x.data_sha256),pinned(x.research,x.research_sha256))
    ref=json.loads(Path(x.reference).read_text())
    require(ref["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD" and ref["protocol_sha256"]==h
            and ref["source_data_sha256"]==x.data_sha256 and
            ref["source_research_sha256"]==x.research_sha256,"QUOTE_REFERENCE_SCOPE")
    result=analyze(p,frames,last,ref)
    result.update(protocol_sha256=h,source_data_sha256=x.data_sha256,
                  source_research_sha256=x.research_sha256)
    out=Path(x.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,allow_nan=False))


if __name__=="__main__":
    main()
