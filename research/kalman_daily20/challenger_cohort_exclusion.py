#!/usr/bin/env python3
"""Fixed admitted-cohort exclusions, not reranking or a new strategy.

Recalculate cash and slot reservations for the retained original trades.
All traded symbols, nonempty fixed research groups, and the retrospectively
identified primary top three are evaluated. No replacement, no new orders,
no source price or execution certification, no forward/live approval.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

import numpy as np
from challenger_execution_audit import replay, NAMES, CAPITAL
from challenger_forward_producer import archive_frames, pinned
from challenger_prequential import load_protocol, require
from challenger_benchmark_validation import daily_return, stats
from challenger_factor_attribution import GROUP, smh_frame, factors, fit, hac
from challenger_stat_validation import holm

TOP3={"AVGO","GOOGL","MU"}
BLOCKS=(5,20,60)
REPS=10000
SEED=2601121


def omit(entries,bars,n,bp,banned):
    h=bp/20000
    cash=CAPITAL
    held=[]
    eq,ow,cw=[],[],[]
    pnl=defaultdict(float)
    by_day=defaultdict(list)
    kept=[t for t in entries if t["symbol"] not in banned]
    for t in kept:
        by_day[t["entry"]].append(t)
    count=0
    for i in range(n):
        opening=cash+sum(x["proceeds"] if x["closed"] else
                         x["qty"]*bars[x["symbol"]][i,0] for x in held)
        for t in by_day[i]:
            require(len(held)<5 and not any(x["symbol"]==t["symbol"] for x in held),
                    "EXCLUSION_CAPACITY")
            spend=min(cash,.2*opening)
            require(spend>1e-7,"EXCLUSION_RETAINED_CASH")
            cash-=spend
            held.append(dict(t,spend=spend,qty=spend/(t["open"]*(1+h)),
                             closed=False,proceeds=0.))
            count+=1
        active=sum(x["qty"]*bars[x["symbol"]][i,0] for x in held if not x["closed"])
        marked=cash+active+sum(x["proceeds"] for x in held if x["closed"])
        require(marked>0,"EXCLUSION_OPEN_EQUITY")
        ow.append(active/marked)
        for x in held:
            if x["exit"]==i:
                require(not x["closed"],"EXCLUSION_EXIT_TWICE")
                x["proceeds"]=x["qty"]*x["exit_price"]*(1-h)
                x["closed"]=True
                pnl[x["symbol"]]+=x["proceeds"]-x["spend"]
            if x["due"]==i:
                require(x["closed"],"EXCLUSION_DUE_NOT_CLOSED")
                cash+=x["proceeds"]
        held=[x for x in held if x["due"]>i]
        active=sum(x["qty"]*bars[x["symbol"]][i,3] for x in held if not x["closed"])
        v=cash+active+sum(x["proceeds"] for x in held if x["closed"])
        require(cash>=-1e-7 and v>0,"EXCLUSION_CASH")
        eq.append(v)
        cw.append(active/v)
    require(not held and count==len(kept)
            and abs(sum(pnl.values())-(eq[-1]-CAPITAL))<1e-6,"EXCLUSION_RECONCILE")
    return dict(equity=np.asarray(eq),ow=np.asarray(ow),cw=np.asarray(cw),trades=count,pnl=dict(pnl))


def significance(pairs):
    d=np.column_stack([x[2] for x in pairs])
    n=len(d)
    mu=d.mean(0)
    c=d-mu
    rows=[]
    for block in BLOCKS:
        ext=np.vstack([c,c[:block]])
        cs=np.vstack([np.zeros(c.shape[1]),ext.cumsum(0)])
        full=cs[block:block+n]-cs[:n]
        rem=n%block
        tail=cs[rem:rem+n]-cs[:n] if rem else None
        rng=np.random.default_rng(SEED+10007*block+2000003)
        sims=[]
        for start in range(0,REPS,128):
            m=min(128,REPS-start)
            ix=rng.integers(0,n,size=(m,n//block+bool(rem)))
            v=full[ix[:,:n//block]].sum(1)
            if rem:
                v+=tail[ix[:,-1]]
            sims.append(v/n)
        z=np.concatenate(sims)
        prob=(1+(np.abs(z)>=np.abs(mu)).sum(0))/(REPS+1)
        lo,hi=mu+np.quantile(z,[.025,.975],axis=0)
        hp=[]
        for j in range(d.shape[1]):
            u=c[:,j]
            v=np.mean(u*u)+sum(2*(1-k/(block+1))*np.dot(u[k:],u[:-k])/n
                              for k in range(1,block+1))
            se=math.sqrt(max(v,0)/n)
            hp.append(math.erfc(abs(mu[j]/se)/math.sqrt(2)) if se else 1.)
        for j,((scenario,key,_),p,h) in enumerate(zip(pairs,holm(prob),holm(hp))):
            rows.append(dict(scenario=scenario,exclusion=key,block=block,
                mean_delta_bp_day=float(mu[j]*10000),
                ci95_low_bp_day=float(lo[j]*10000),ci95_high_bp_day=float(hi[j]*10000),
                p_raw=float(prob[j]),p_holm=float(p),hac_p=float(hp[j]),hac_holm=float(h)))
    return rows


def analyze(p,frames,smh,last,ref):
    dates,_,entries,curves,bars=replay(p,frames,last)
    require(len(dates)==727 and last=="2026-11-23","EXCLUSION_FROZEN_WINDOW")
    _,on,day=factors(p,frames,smh,dates)
    years=np.asarray([d[:4] for d in dates])
    results={}
    pairs=[]
    for name in NAMES:
        bp=int(name.split("_")[1])
        e=entries[name]
        base=omit(e,bars,len(dates),bp,set())
        bstats=stats(base["equity"],dates)
        reference=ref["scenarios"][name]
        require(np.allclose(base["equity"],curves[name],rtol=0,atol=1e-7)
                and abs(bstats["total_return"]-reference["total_return"])<1e-10
                and abs(bstats["eod_mdd"]-reference["eod_mdd"])<1e-10
                and base["trades"]==reference["trades"],"EXCLUSION_BASE_PARITY")
        y=daily_return(base["equity"])
        symbols=sorted({t["symbol"] for t in e})
        groups=sorted({GROUP[s] for s in symbols})
        variants={"BASE":set()}
        variants.update({"SYM_"+s:{s} for s in symbols})
        variants.update({"GROUP_"+g:{s for s in symbols if GROUP[s]==g} for g in groups})
        variants["TOP3_PRIMARY"]=TOP3
        scenario=name.removesuffix("_K1+K3")
        out={}
        results[scenario]=out
        for key,banned in variants.items():
            b=omit(e,bars,len(dates),bp,banned)
            r=daily_return(b["equity"])
            adj=on*np.r_[0.,b["cw"][:-1]][:,None]+day*b["ow"][:,None]
            x,coef,resid,inv=fit(r,adj)
            _,prior,_,_=fit(r[years<"2026"],adj[years<"2026"])
            test=years=="2026"
            row=stats(b["equity"],dates)
            row.update(trades=b["trades"],removed=base["trades"]-b["trades"],
                removed_symbols=sorted(banned),avg_open_exposure=float(b["ow"].mean()),
                avg_close_exposure=float(b["cw"].mean()),
                alpha_annual_arith_pct=float(coef[0]*25200),
                alpha_hac20_p=hac(x,coef,resid,inv,20)[0],
                prior_fit_2026_alpha_pct=float((r[test]-adj[test]@prior[1:]).mean()*25200),
                accounting_only_return=float(bstats["total_return"]-
                    sum(v for s,v in base["pnl"].items() if s in banned)/CAPITAL))
            require(row["removed"]==sum(t["symbol"] in banned for t in e),
                    "EXCLUSION_NO_REPLACEMENT")
            out[key]=row
            if key!="BASE":
                pairs.append((scenario,key,r-y))
    require(len(pairs)==91,"EXCLUSION_FAMILY_PARITY")
    return dict(version="kalman-challenger-locked-cohort-exclusion-v1",
        status="RETROSPECTIVE_RESEARCH_HOLD",research_only=True,approved_live=False,
        source_finality_certified=False,forward_signals_created=0,model_selection_allowed=False,
        first_session=dates[0],last_session=dates[-1],sessions=len(dates),
        tests_per_block=len(pairs),replications_per_block=REPS,
        results=results,significance=significance(pairs),
        limitations=["Fixed admitted trades; no reranking, replacement, or new eligible trade.",
            "Cash and capital reservations recalculated with unchanged price barriers, actual exit-day proxies and cost.",
            "Primary top three picked from earlier inspected PnL; retrospective sensitivity only.",
            "Paired tests concern change versus full strategy, not positivity of each variant.",
            "Holm covers all 91 exclusions including duplicate single-symbol group masks, not the entire adaptive search.",
            "Exposure alpha is a proxy regression with zero cash yield; not causal or independent forward evidence."])


def self_test():
    bars={"A":np.array([[100,101,99,100],[100,106,99,105],
                         [105,106,104,105],[105,106,104,105]],float),
          "B":np.array([[100,101,99,100],[100,101,95,96],
                         [96,97,95,96],[96,97,95,96]],float)}
    entries=[dict(symbol="A",entry=0,exit=1,due=3,open=100.,exit_price=105.),
             dict(symbol="B",entry=0,exit=1,due=3,open=100.,exit_price=96.)]
    x=omit(entries,bars,4,30,set())
    a=omit(entries,bars,4,30,{"B"})
    c=omit(entries,bars,4,30,{"A","B"})
    h=.0015
    require(abs(a["equity"][-1]-(80000+20000*1.05*(1-h)/(1+h)))<1e-7
            and a["trades"]==1 and x["trades"]==2 and c["trades"]==0
            and np.all(c["equity"]==CAPITAL)
            and np.allclose(a["cw"][1:],0) and a["equity"][-1]>x["equity"][-1],
            "EXCLUSION_TEST_CASH_AND_NO_REPLACEMENT")
    print("CHALLENGER_EXCLUSION_SYNTHETIC_PASS")


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
            "EXCLUSION_INPUTS")
    p,h=load_protocol()
    raw=pinned(args.data,args.data_sha256)
    last,frames=archive_frames(p,raw,pinned(args.research,args.research_sha256))
    ref=json.loads(Path(args.reference).read_text())
    require(ref["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD" and ref["protocol_sha256"]==h
            and ref["source_data_sha256"]==args.data_sha256
            and ref["source_research_sha256"]==args.research_sha256,"EXCLUSION_REFERENCE_SCOPE")
    result=analyze(p,frames,smh_frame(raw,last),last,ref)
    result.update(protocol_sha256=h,source_data_sha256=args.data_sha256,
                  source_research_sha256=args.research_sha256)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(status=result["status"],sessions=result["sessions"],
        tests_per_block=result["tests_per_block"],
        key_results={s:{k:{a:v[a] for a in ("total_return","eod_mdd","trades","alpha_annual_arith_pct")}
                       for k,v in x.items() if k in ("BASE","SYM_AVGO","SYM_GOOGL","SYM_MU","GROUP_SEMI","TOP3_PRIMARY")}
                     for s,x in result["results"].items()},
        holm_pass={b:sum(r["p_holm"]<.05 for r in result["significance"] if r["block"]==b)
                   for b in BLOCKS})))

if __name__=="__main__":
    main()
