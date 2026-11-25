#!/usr/bin/env python3
"""Frozen K1+K3 exposure/risk/timing benchmark diagnostics, research only.

Replay the unchanged producer ledger; compare same-date SPY/QQQ with zero
cash yield and equal proportional trading friction. Constant weights fitted
to the whole sample and realized stock exit dates are retrospective controls,
not executable strategies. Lagged volatility weights use a close-mark proxy.
No orders, new seals, scheduling, Drive, model fitting, or promotion.
"""
import argparse
from pathlib import Path
import json
import math
from datetime import timedelta

import numpy as np
import pandas as pd

from challenger_forward_producer import (
    Book, advance, archive_frames, calendar_names, daily_inputs, pinned,
    SEED_START,
)
from challenger_prequential import load_protocol, require
from challenger_stat_validation import holm, hac_p

CAPITAL = 100000.
COHORTS = ("20", "16")
COSTS = (30, 50)
ETFS = ("SPY", "QQQ")
KINDS = ("EXPOSURE", "VOL", "EXIT_DAY", "FOUR_DAY", "ROLL63")
BLOCKS = (5, 20, 60)
REPS = 10000
SEED = 2601121
WARMUP = 63


def daily_return(eq):
    eq = np.asarray(eq, float)
    require(np.isfinite(eq).all() and (eq>0).all(), "BENCHMARK_EQUITY")
    return eq / np.r_[CAPITAL, eq[:-1]] - 1


def stats(eq, dates):
    eq = np.asarray(eq, float)
    r = daily_return(eq)
    sd = r.std(ddof=1)
    peaks = np.maximum.accumulate(np.r_[CAPITAL, eq])[1:]
    y = pd.Series(eq, index=dates).groupby(pd.Index(dates).str[:4]).last()
    return dict(total_return=float(eq[-1]/CAPITAL-1),
                eod_mdd=float(np.min(eq/peaks-1)),
                annualized_volatility=float(sd*math.sqrt(252)),
                annualized_sharpe_zero_rate=float(r.mean()/sd*math.sqrt(252)) if sd else None,
                annual_returns={k:float(v) for k,v in (y/y.shift(fill_value=CAPITAL)-1).items()})


def replay(p, frames, last):
    _,_,names=calendar_names("2022-01-03",
            (pd.Timestamp(last)+pd.Timedelta(days=35)).date().isoformat())
    begin=names.index(SEED_START)
    end=names.index(last)
    dates=names[begin:end+1]
    books={f"{c}_{b}_K1+K3":Book(f"{c}_{b}_K1+K3",names)
           for c in COHORTS for b in COSTS}
    out={s:dict(equity=[],open_weights=[],close_weights=[],entries=[],exits={},exit_net_pnl={}) for s in books}
    prices={s:{"open":[],"close":[]} for s in ETFS}
    clocks,previous={},None
    for i in range(begin,end+1):
        inputs=daily_inputs(p,frames,names,i)
        bars=inputs["bars"]
        marked={s:b.marked(bars,"open") for s,b in books.items()}
        old_active={s:sum(pos["qty"]*bars[pos["symbol"]]["open"]
                  for pos in b.slots if not pos["closed"]) for s,b in books.items()}
        current,traces=advance(p,books,clocks,names,i,inputs,previous)
        for s,b in books.items():
            t=traces[s]
            o=out[s]
            gross=sum(e["qty"]*e["open"] for e in t["entries"])
            spend=sum(e["spend"] for e in t["entries"])
            after=marked[s]+gross-spend
            require(after>0,"BENCHMARK_OPEN_MARK")
            o["open_weights"].append((old_active[s]+gross)/after)
            o["equity"].append(t["equity"])
            o["close_weights"].append(sum(pos["qty"]*bars[pos["symbol"]]["close"]
                for pos in b.slots if not pos["closed"])/t["equity"])
            o["entries"].append([dict(weight=e["spend"]/marked[s],
                due=e["due"]-begin,key=(e["signal"],e["symbol"])) for e in t["entries"]])
            for e in t["exits"]:
                key=(e["signal"],e["symbol"])
                require(key not in o["exits"],"BENCHMARK_DUPLICATE_EXIT")
                o["exits"][key]=i-begin
                o["exit_net_pnl"][key]=e["net_pnl"]
        for s in ETFS:
            for k in ("open","close"):
                prices[s][k].append(bars[s][k])
        previous=current
    for s,b in books.items():
        o=out[s]
        require(not b.slots and sum(map(len,o["entries"]))==len(o["exits"])==b.trades,
                "BENCHMARK_UNSETTLED_REPLAY")
        require(abs(b.free-CAPITAL-b.pnl)<1e-6,"BENCHMARK_STOCK_LEDGER")
        require(abs(sum(o["exit_net_pnl"].values())-b.pnl)<1e-6,
                "BENCHMARK_EXIT_PNL_PARITY")
        o["trades"]=b.trades
        o["equity"]=np.asarray(o["equity"])
    return dates,out,prices


def weight_book(close,w,bp):
    """At preceding close rebalance to w[k] with half-cost per side."""
    close=np.asarray(close,float)
    w=np.asarray(w,float)
    require(len(close)==len(w) and (close>0).all() and np.isfinite(close).all()
            and ((w>=0)&(w<=1)).all(),"BENCHMARK_WEIGHT_INPUT")
    h=bp/20000
    cash=CAPITAL
    stock=0.
    eq=[cash]
    fees=0.
    weights=[0.]
    for k in range(1,len(close)):
        v=cash+stock
        goal=w[k]*v
        new=(w[k]*(v+h*stock)/(1+w[k]*h) if goal>=stock
             else w[k]*(v-h*stock)/(1-w[k]*h))
        delta=new-stock
        fee=h*abs(delta)
        cash-=delta+fee
        fees+=fee
        stock=new
        weights.append(stock/(stock+cash))
        stock*=close[k]/close[k-1]
        if k==len(close)-1:
            fee=h*stock
            fees+=fee
            cash+=stock-fee
            stock=0.
        eq.append(cash+stock)
        require(cash>=-1e-7 and eq[-1]>0,"BENCHMARK_WEIGHT_CASH")
    return dict(equity=np.asarray(eq),fees=fees,weights=np.asarray(weights),cash_clips=0)


def timing_book(stock,price,bp,planned):
    """Copy admitted entry weights; sell ETF at actual stock exit-day CLOSE,
    or at planned fourth close. Equal tick/time-of-day exposure not asserted.
    """
    h=bp/20000
    cash=CAPITAL
    held=[]
    eq=[]
    weights=[]
    fees=0.
    clips=0
    for k,(op,cl) in enumerate(zip(price["open"],price["close"])):
        v=cash+sum(pos["proceeds"] if pos["closed"] else pos["qty"]*op for pos in held)
        for p in stock["entries"][k]:
            want=p["weight"]*v
            spend=min(cash,want)
            clips+=int(spend+1e-7<want)
            cash-=spend
            qty=spend/(op*(1+h))
            fees+=qty*op*h
            exit_i=p["due"] if planned else stock["exits"][p["key"]]
            require(k<=exit_i<=p["due"],"BENCHMARK_EXIT_SCOPE")
            held.append(dict(qty=qty,exit=exit_i,due=p["due"],closed=False,proceeds=0.))
        active=sum(pos["qty"]*op for pos in held if not pos["closed"])
        weights.append(active/(cash+active+sum(pos["proceeds"] for pos in held if pos["closed"])))
        for pos in held:
            if not pos["closed"] and pos["exit"]==k:
                gross=pos["qty"]*cl
                pos["proceeds"]=gross*(1-h)
                pos["closed"]=True
                fees+=gross*h
            if pos["due"]==k:
                require(pos["closed"],"BENCHMARK_DUE_OPEN")
                cash+=pos["proceeds"]
        held=[pos for pos in held if pos["due"]>k]
        equity=cash+sum(pos["proceeds"] if pos["closed"] else pos["qty"]*cl for pos in held)
        require(cash>=-1e-7 and equity>0 and len(held)<=5,"BENCHMARK_TIMING_CASH")
        eq.append(equity)
    require(not held,"BENCHMARK_TIMING_UNSETTLED")
    return dict(equity=np.asarray(eq),fees=fees,weights=np.asarray(weights),cash_clips=clips)


def rolling_weights(r,mkt):
    w=np.zeros(len(r))
    for k in range(WARMUP,len(r)):
        v=mkt[k-WARMUP:k].std(ddof=1)
        if v>0:
            w[k]=min(1.,r[k-WARMUP:k].std(ddof=1)/v)
    return w


def risk_match(r,cl,bp):
    target=r.std(ddof=1)
    lo,hi=0.,1.
    require(daily_return(weight_book(cl,np.ones(len(cl)),bp)["equity"]).std(ddof=1)>=target,
            "BENCHMARK_UNLEVERED_RISK_MATCH_INFEASIBLE")
    for _ in range(42):
        mid=(lo+hi)/2
        trial=weight_book(cl,np.full(len(cl),mid),bp)
        if daily_return(trial["equity"]).std(ddof=1)<target:
            lo=mid
        else:
            hi=mid
    b=weight_book(cl,np.full(len(cl),(lo+hi)/2),bp)
    require(abs(daily_return(b["equity"]).std(ddof=1)-target)<1e-12,
            "BENCHMARK_VOL_MATCH_PRECISION")
    return b


def significance(pairs):
    # 40 paired comparisons, adjusted jointly per block length; rolling
    # comparisons use only the common 664-session post-warmup interval.
    rows=[]
    for block in BLOCKS:
        batch=[]
        for off in (0,WARMUP):
            selected=[p for p in pairs if p[2]==off]
            d=np.column_stack([p[3] for p in selected])
            n=len(d)
            mu=d.mean(axis=0)
            centered=d-mu
            rng=np.random.default_rng(SEED+block*10007+2000003+off)
            sims=[]
            for start in range(0,REPS,128):
                b=min(128,REPS-start)
                a=rng.integers(0,n,size=(b,(n+block-1)//block))
                ix=((a[:,:,None]+np.arange(block))%n).reshape(b,-1)[:,:n]
                sims.append(centered[ix].mean(axis=1))
            z=np.concatenate(sims)
            p=(1+(np.abs(z)>=np.abs(mu)).sum(axis=0))/(REPS+1)
            lo,hi=mu+np.quantile(z,[.025,.975],axis=0)
            hp=hac_p(d,block)
            for i,(name,key,_,_) in enumerate(selected):
                batch.append(dict(scenario=name,benchmark=key,block=block,sessions=n,
                    mean_diff_bp_day=float(mu[i]*10000),ci95_low_bp_day=float(lo[i]*10000),
                    ci95_high_bp_day=float(hi[i]*10000),p_raw=float(p[i]),p_hac=float(hp[i])))
        require(len(batch)==40,"BENCHMARK_HYPOTHESIS_COUNT")
        for row,p,h in zip(batch,holm([x["p_raw"] for x in batch]),holm([x["p_hac"] for x in batch])):
            row.update(p_holm=float(p),p_hac_holm=float(h))
        rows.extend(batch)
    return rows


def analyze(p,frames,last,reference):
    dates,stocks,prices=replay(p,frames,last)
    require(len(dates)==727 and last=="2026-11-23","BENCHMARK_FROZEN_WINDOW")
    results={}
    pairs=[]
    for c in COHORTS:
        for bp in COSTS:
            name=f"{c}_{bp}_K1+K3"
            stock=stocks[name]
            st=stats(stock["equity"],dates)
            base=reference["scenarios"][name]
            require(abs(st["total_return"]-base["total_return"])<1e-10 and
                    abs(st["eod_mdd"]-base["eod_mdd"])<1e-10 and
                    stock["trades"]==base["trades"],"BENCHMARK_REHEARSAL_PARITY")
            st.update(trades=stock["trades"],avg_open_exposure=float(np.mean(stock["open_weights"])),
                      avg_close_exposure=float(np.mean(stock["close_weights"])),
                      active_open_days=int(np.count_nonzero(stock["open_weights"])))
            result=dict(strategy=st,benchmarks={})
            results[name]=result
            r=daily_return(stock["equity"])
            for s in ETFS:
                price=prices[s]
                cl=np.asarray(price["close"])
                mkt=np.r_[0.,cl[1:]/cl[:-1]-1]
                arms=dict(EXPOSURE=weight_book(cl,np.full(len(cl),st["avg_open_exposure"]),bp),
                          VOL=risk_match(r,cl,bp),
                          EXIT_DAY=timing_book(stock,price,bp,False),
                          FOUR_DAY=timing_book(stock,price,bp,True),
                          ROLL63=weight_book(cl,rolling_weights(r,mkt),bp))
                result["benchmarks"][s+"_BUY_HOLD"]=stats(weight_book(cl,np.ones(len(cl)),bp)["equity"],dates)
                for kind,b in arms.items():
                    key=s+"_"+kind
                    q=stats(b["equity"],dates)
                    q.update(avg_exposure=float(np.mean(b["weights"][1:])),
                             fees=float(b["fees"]),cash_clips=b["cash_clips"])
                    br=daily_return(b["equity"])
                    off=WARMUP if kind=="ROLL63" else 0
                    if off:
                        q.update(common_strategy_return=float(np.prod(1+r[off:])-1),
                                 common_benchmark_return=float(np.prod(1+br[off:])-1),
                                 common_strategy_vol=float(r[off:].std(ddof=1)*math.sqrt(252)),
                                 common_benchmark_vol=float(br[off:].std(ddof=1)*math.sqrt(252)))
                    result["benchmarks"][key]=q
                    pairs.append((name,key,off,r[off:]-br[off:]))
    sig=significance(pairs)
    return dict(version="kalman-challenger-benchmark-validation-v1",
        status="RETROSPECTIVE_RESEARCH_HOLD",research_only=True,approved_live=False,
        source_finality_certified=False,forward_signals_created=0,model_selection_allowed=False,
        first_session=dates[0],last_session=dates[-1],sessions=len(dates),
        hypotheses_per_block=40,replications_per_block=REPS,results=results,significance=sig,
        limitations=["Zero cash yield; not factor-adjusted alpha.",
                     "Full-sample static exposure and volatility matching are ex-post controls.",
                     "Matching stock exit-day close does not match actual intraday fill; exit dates use realized stock outcomes.",
                     "Rolling 63-day target uses previous returns only; rebalancing at preceding close is an optimistic price proxy.",
                     "Same nominal fee per traded dollar, not verified spreads/slippage.",
                     "Resampling retained returns does not refit risk targets or rerun trading on sampled market histories.",
                     "Holm correction covers this family, not prior adaptive search; no independent forward evidence."])


def self_test():
    cl=np.full(100,100.)
    b=weight_book(cl,np.zeros(100),30)
    require(np.array_equal(b["equity"],np.full(100,CAPITAL)),"BENCHMARK_CASH_TEST")
    b=weight_book(cl,np.ones(100),30)
    require(abs(b["equity"][-1]-CAPITAL*(1-.0015)/(1+.0015))<1e-7,
            "BENCHMARK_ROUNDTRIP_TEST")
    rng=np.random.default_rng(4)
    r,m=rng.normal(0,.005,100),rng.normal(0,.01,100)
    a=rolling_weights(r,m)
    r[80:]=9.
    require(np.array_equal(a[:81],rolling_weights(r,m)[:81]),"BENCHMARK_NO_FUTURE_WEIGHT")
    stock=dict(entries=[[dict(weight=.2,due=3,key=("s","x"))],[],[],[]],
               exits={("s","x"):1})
    price=dict(open=[100,100,100,100],close=[100,102,103,104])
    x=timing_book(stock,price,30,False)
    y=timing_book(stock,price,30,True)
    require(x["equity"][-1]<y["equity"][-1] and
            abs(x["equity"][-1]-(80000+20000*1.02*(1-.0015)/(1+.0015)))<1e-7,
            "BENCHMARK_TIMING_TEST")
    print("CHALLENGER_BENCHMARK_VALIDATION_SYNTHETIC_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    for k in ("data","data-sha256","research","research-sha256","reference","out"):
        a.add_argument("--"+k)
    args=a.parse_args()
    if args.self_test:
        self_test()
        return
    require(all([args.data,args.data_sha256,args.research,args.research_sha256,args.reference,args.out]),
            "BENCHMARK_ARGUMENTS")
    p,h=load_protocol()
    last,frames=archive_frames(p,pinned(args.data,args.data_sha256),
                               pinned(args.research,args.research_sha256))
    ref=json.loads(Path(args.reference).read_text())
    require(ref["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD" and ref["protocol_sha256"]==h
            and ref["source_data_sha256"]==args.data_sha256
            and ref["source_research_sha256"]==args.research_sha256,"BENCHMARK_REFERENCE_SCOPE")
    result=analyze(p,frames,last,ref)
    result.update(protocol_sha256=h,source_data_sha256=args.data_sha256,
                  source_research_sha256=args.research_sha256)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(status=result["status"],sessions=result["sessions"],
             results={k:{"strategy":v["strategy"],"benchmarks":v["benchmarks"]}
                      for k,v in result["results"].items()},
             holm_rejections={b:sum(x["p_holm"]<.05 for x in result["significance"] if x["block"]==b)
                              for b in BLOCKS}),allow_nan=False))


if __name__=="__main__":
    main()
