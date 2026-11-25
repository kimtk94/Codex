#!/usr/bin/env python3
"""Daily ledger execution-risk sensitivity and exact 15-minute coverage audit.

Research only. A fixed admitted cohort is stressed, not re-admitted at the new
cost. No actual quote/fill claim. Optional private input manifest is never
committed or uploaded to public CI; report contains aggregate counts only.
"""
import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from challenger_forward_producer import (
    Book, advance, archive_frames, calendar_names, daily_inputs, pinned, SEED_START,
)
from challenger_prequential import load_protocol, require, sha

CAPITAL=100000.
EXTRA=(0,5,10,20,50)
NAMES=tuple(f"{c}_{bp}_K1+K3" for c in (20,16) for bp in (30,50))
OHLC=["open","high","low","close"]


def replay(p,frames,last):
    cal,sessions,names=calendar_names("2022-01-03",
        (pd.Timestamp(last)+pd.Timedelta(days=35)).date().isoformat())
    begin,end=names.index(SEED_START),names.index(last)
    dates=names[begin:end+1]
    require(len(dates)==727 and last=="2026-11-23","EXECUTION_FROZEN_WINDOW")
    grids={str(s.date()):pd.date_range(cal.session_open(s),cal.session_close(s),
        freq="15min",inclusive="left") for s in sessions[begin:end+1]}
    books={s:Book(s,names) for s in NAMES}
    entries={s:{} for s in books}
    curves={s:[] for s in books}
    bars={sym:[] for sym in p["universe"]}
    prev=None
    clocks={}
    for i in range(begin,end+1):
        inputs=daily_inputs(p,frames,names,i)
        for sym in bars:
            bars[sym].append([inputs["bars"][sym][k] for k in OHLC])
        current,traces=advance(p,books,clocks,names,i,inputs,prev)
        for s,t in traces.items():
            curves[s].append(t["equity"])
            for e in t["entries"]:
                key=(e["signal"],e["symbol"])
                require(key not in entries[s],"EXECUTION_DUPLICATE_ENTRY")
                entries[s][key]=dict(symbol=e["symbol"],signal=e["signal"],
                    entry=i-begin,due=e["due"]-begin,open=e["open"],
                    stop=e["stop"],target=e["target"])
            for e in t["exits"]:
                key=(e["signal"],e["symbol"])
                x=entries[s][key]
                require("exit" not in x,"EXECUTION_DUPLICATE_EXIT")
                x.update(exit=i-begin,exit_price=e["price"],reason=e["reason"])
        prev=current
    for s,b in books.items():
        require(not b.slots and len(entries[s])==b.trades and
                all("exit" in e for e in entries[s].values()),"EXECUTION_UNSETTLED")
    return dates,grids,{s:list(t.values()) for s,t in entries.items()},\
        {s:np.asarray(c) for s,c in curves.items()},\
        {s:np.asarray(b) for s,b in bars.items()}


def summary(eq):
    e=np.asarray(eq)
    peak=np.maximum.accumulate(np.r_[CAPITAL,e])[1:]
    return dict(total_return=float(e[-1]/CAPITAL-1),
                eod_mdd=float((e/peak-1).min()))


def stressed(entries,bars,n,bp,extra,target_first=False):
    # Same entry/exit sessions and original planned levels, same slot lock.
    # Adverse multiplicative execution cost is EXTRA per side on top of base.
    h=bp/20000
    s=extra/10000
    cash=CAPITAL
    held=[]
    eq=[]
    by_day=defaultdict(list)
    for t in entries:
        by_day[t["entry"]].append(t)
    ntr=0
    rr_pass=0
    for i in range(n):
        opening=cash+sum(x["proceeds"] if x["closed"]
                          else x["qty"]*bars[x["symbol"]][i,0] for x in held)
        for t in by_day[i]:
            require(len(held)<5 and not any(x["symbol"]==t["symbol"] for x in held),
                    "EXECUTION_CAPACITY_PARITY")
            spend=min(cash,.2*opening)
            require(spend>0,"EXECUTION_ADMITTED_CASH")
            entry=t["open"]*(1+h)*(1+s)
            stop=t["stop"]*(1-h)*(1-s)
            target=t["target"]*(1-h)*(1-s)
            require(entry>stop,"EXECUTION_INVALID_RISK")
            rr_pass+=int((target-entry)/(entry-stop)>=2)
            cash-=spend
            held.append(dict(t,qty=spend/entry,closed=False,proceeds=0.))
            ntr+=1
        for x in held:
            if x["exit"]==i:
                require(not x["closed"],"EXECUTION_EXIT_TWICE")
                price=x["target"] if target_first and x["reason"]=="BOTH_TOUCH_STOP_FIRST" else x["exit_price"]
                x["proceeds"]=x["qty"]*price*(1-h)*(1-s)
                x["closed"]=True
            if x["due"]==i:
                require(x["closed"],"EXECUTION_DUE_NOT_CLOSED")
                cash+=x["proceeds"]
        held=[x for x in held if x["due"]>i]
        val=cash+sum(x["proceeds"] if x["closed"] else
                     x["qty"]*bars[x["symbol"]][i,3] for x in held)
        require(cash>=-1e-7 and val>0,"EXECUTION_CASH")
        eq.append(val)
    require(not held and ntr==len(entries),"EXECUTION_FINAL_STATE")
    return np.asarray(eq),dict(summary(eq),trades=ntr,planned_exact_rr_pass=rr_pass)


def private_frames(path,expected_sha):
    raw=pinned(path,expected_sha)
    m=json.loads(raw)
    require(m["version"]=="kalman-private-15m-input-v1" and m["research_only"] is True
            and m["timestamp_convention"]=="UTC_BAR_START"
            and isinstance(m["files"],list),"EXECUTION_PRIVATE_MANIFEST")
    out={}
    for x in m["files"]:
        sym=x["symbol"]
        require(isinstance(sym,str) and sym not in out,"EXECUTION_PRIVATE_SYMBOL")
        source=Path(x["path"])
        require(source.is_file(),"EXECUTION_PRIVATE_FILE")
        raw=pinned(source,x["sha256"])
        import io
        f=pd.read_parquet(io.BytesIO(raw))
        require(set(["candle_time_utc",*OHLC]).issubset(f.columns),
                "EXECUTION_PRIVATE_SCHEMA")
        idx=pd.DatetimeIndex(pd.to_datetime(f["candle_time_utc"],errors="raise"))
        require(idx.tz is not None and not idx.has_duplicates and not idx.isna().any(),
                "EXECUTION_PRIVATE_TIME")
        f=f[OHLC].apply(pd.to_numeric,errors="raise")
        f.index=idx.tz_convert("UTC")
        f=f.sort_index()
        v=f.to_numpy(float)
        require(np.isfinite(v).all() and (v>0).all() and
                (v[:,2]<=np.minimum(v[:,0],v[:,3])).all() and
                (v[:,1]>=np.maximum(v[:,0],v[:,3])).all(),"EXECUTION_PRIVATE_OHLC")
        out[sym]=f
    return out


def bar_outcome(t,blocks):
    # Daily entry and levels fixed; bar opens are proxies, not quote fills.
    for j,f in enumerate(blocks):
        for k,(o,h,l,c) in enumerate(f):
            if not (j==0 and k==0):
                if o<=t["stop"]:
                    return ("STOP_GAP" if k==0 else "STOP"),j
                if o>=t["target"]:
                    return ("TARGET_GAP_CAPPED" if k==0 else "TARGET"),j
            if l<=t["stop"] and h>=t["target"]:
                return "BOTH_TOUCH_STOP_FIRST",j
            if l<=t["stop"]:
                return "STOP",j
            if h>=t["target"]:
                return "TARGET",j
    return "TIME_CLOSE",len(blocks)-1


def coverage(entries,dates,grids,bars,private):
    windows={(t["symbol"],t["signal"],t["entry"],t["due"]) for t in entries}
    days={(s,i) for s,_,e,d in windows for i in range(e,d+1)}
    covered={(s,i) for s,i in days if s in private and
             grids[dates[i]].isin(private[s].index).all()}
    full=0
    agree=0
    provisional=0
    max_delta=0.
    complete_windows=set()
    for t in entries:
        s=t["symbol"]
        ids=range(t["entry"],t["due"]+1)
        if not all((s,i) in covered for i in ids):
            continue
        full+=1
        complete_windows.add((s,t["signal"],t["entry"],t["due"]))
        blocks=[private[s].loc[grids[dates[i]],OHLC].to_numpy(float) for i in ids]
        agg=np.asarray([[b[0,0],b[:,1].max(),b[:,2].min(),b[-1,3]] for b in blocks])
        daily=bars[s][t["entry"]:t["due"]+1]
        diff=float(np.max(np.abs(agg/daily-1)))
        provisional+=int(diff<=.002)
        max_delta=max(max_delta,diff)
        outcome,offset=bar_outcome(t,blocks)
        agree+=int((outcome,offset)==(t["reason"],t["exit"]-t["entry"]))
    return dict(trades=len(entries),unique_windows=len(windows),
                required_symbol_days=len(days),
                required_15m_bars=sum(len(grids[dates[i]]) for _,i in days),
                supplied_complete_symbol_days=len(covered),
                supplied_complete_trades=full,
                supplied_complete_unique_windows=len(complete_windows),
                exit_type_and_day_agree=agree,
                provisional_ohlc_20bp_pass=provisional,
                max_ohlc_relative_difference=max_delta if full else None)


def analyze(p,frames,last,ref,private):
    dates,grids,entries,curves,bars=replay(p,frames,last)
    results={}
    all_trades=[]
    for name in NAMES:
        bp=int(name.split("_")[1])
        e=entries[name]
        all_trades.extend(e)
        base=ref["scenarios"][name]
        raw=summary(curves[name])
        require(abs(base["total_return"]-raw["total_return"])<1e-10 and
                abs(base["eod_mdd"]-raw["eod_mdd"])<1e-10 and base["trades"]==len(e),
                "EXECUTION_REFERENCE_PARITY")
        tests={}
        for cost in EXTRA:
            eq,res=stressed(e,bars,len(dates),bp,cost)
            if cost==0:
                require(np.allclose(eq,curves[name],rtol=0,atol=1e-7) and
                        res["planned_exact_rr_pass"]==len(e),"EXECUTION_DAILY_PARITY")
            tests[str(cost)]=res
        _,target=stressed(e,bars,len(dates),bp,0,True)
        results[name]=dict(coverage=coverage(e,dates,grids,bars,private),
             exit_types=dict(Counter(t["reason"] for t in e)),
             additional_slippage_per_side_bp=tests,target_first_sensitivity=target)
    # Union is over actual admitted symbol/signal windows, not all candidates.
    union=coverage(all_trades,dates,grids,bars,private)
    require(union["unique_windows"]==193 and union["required_symbol_days"]==769,
            "EXECUTION_UNION_PARITY")
    return dict(version="kalman-challenger-execution-audit-v1",
        status="RETROSPECTIVE_EXECUTION_RESEARCH_HOLD",research_only=True,
        approved_live=False,forward_signals_created=0,source_finality_certified=False,
        actual_quote_fills_verified=False,sessions=len(dates),
        supplied_intraday_symbols=len(private),union=union,scenarios=results,
        limitations=["Fixed admitted cohort, not a new higher-cost RR2-admitted strategy.",
            "Extra adverse per-side friction is hypothetical, not measured slippage.",
            "Daily/15m OHLC are price proxies; no NBBO, queue, liquidity or fill proof.",
            "20bp OHLC tolerance is provisional and not adjustment equivalence.",
            "No private bars, dates or trade-level records in the aggregate report.",
            "Historical research window previously inspected; no independent forward evidence."])


def self_test():
    t=dict(symbol="X",signal="test",entry=0,due=3,exit=1,open=100.,
           stop=98.,target=106.,exit_price=98.,reason="BOTH_TOUCH_STOP_FIRST")
    b={"X":np.array([[100,101,99,100],[100,107,97,100],
                     [100,101,99,100],[100,101,99,100]],float)}
    eq,x=stressed([t],b,4,30,0)
    _,y=stressed([t],b,4,30,10)
    _,z=stressed([t],b,4,30,0,True)
    require(x["planned_exact_rr_pass"]==1 and y["total_return"]<x["total_return"]
            <z["total_return"],"EXECUTION_STRESS_TEST")
    require(abs(eq[-1]-(80000+20000*.98*(1-.0015)/(1+.0015)))<1e-7,
            "EXECUTION_CASH_TEST")
    require(bar_outcome(t,[b["X"][:2]])==("BOTH_TOUCH_STOP_FIRST",0),
            "EXECUTION_BOTH_TOUCH_TEST")
    require(bar_outcome(t,[np.array([[100,106,99,105],[105,105,97,98]])])==("TARGET",0),
            "EXECUTION_BAR_ORDER_TEST")
    print("CHALLENGER_EXECUTION_AUDIT_SYNTHETIC_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    for k in ("data","data-sha256","research","research-sha256","reference","out",
              "private-manifest","private-manifest-sha256"):
        a.add_argument("--"+k)
    x=a.parse_args()
    if x.self_test:
        self_test()
        return
    require(all([x.data,x.data_sha256,x.research,x.research_sha256,x.reference,x.out]),
            "EXECUTION_INPUTS")
    require(bool(x.private_manifest)==bool(x.private_manifest_sha256),
            "EXECUTION_PRIVATE_MANIFEST_PAIR")
    import os
    require(not(x.private_manifest and os.environ.get("GITHUB_ACTIONS")),
            "EXECUTION_PRIVATE_INPUT_FORBIDDEN_IN_PUBLIC_CI")
    p,h=load_protocol()
    last,frames=archive_frames(p,pinned(x.data,x.data_sha256),pinned(x.research,x.research_sha256))
    ref=json.loads(Path(x.reference).read_text())
    require(ref["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD" and ref["protocol_sha256"]==h
            and ref["source_data_sha256"]==x.data_sha256
            and ref["source_research_sha256"]==x.research_sha256,"EXECUTION_REFERENCE_SCOPE")
    private=private_frames(x.private_manifest,x.private_manifest_sha256) if x.private_manifest else {}
    result=analyze(p,frames,last,ref,private)
    result.update(protocol_sha256=h,source_data_sha256=x.data_sha256,
                  source_research_sha256=x.research_sha256)
    out=Path(x.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,allow_nan=False))


if __name__=="__main__":
    main()
