#!/usr/bin/env python3
"""Retrospective factor-proxy attribution; no official FF data or execution.

Fixed four cohorts and four regression specifications. Joint circular pairs
bootstrap refits all coefficients on each draw. No new model selection or
forward approval. All factors use the already pinned adjusted OHLC archive.
"""
import argparse
import io
import json
import math
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
from challenger_forward_producer import archive_frames, pinned, safe_zip
from challenger_prequential import load_protocol, require
from challenger_benchmark_validation import replay, daily_return, stats
from challenger_stat_validation import holm

FACTORS=("SPY","QQQ_minus_SPY","SMH_minus_QQQ","IWM_minus_SPY","MOM20_16")
GROUPS={"SEMI":["AMD","AVGO","MU","NVDA"],
        "OTHER_TECH":["AAPL","MSFT","PLTR","IONQ"],
        "INTERNET":["GOOGL","META"],"CONSUMER":["AMZN","TSLA"],
        "FINANCE":["JPM"],"ENERGY":["XOM"],"CRYPTO_LINKED":["COIN","MSTR"],
        "INDEX_ETF":["SPY","QQQ","QLD","IWM"]}
GROUP={s:g for g,ss in GROUPS.items() for s in ss}
BLOCKS=(5,20,60)
REPS=10000
SEED=2601121


def smh_frame(raw,last):
    with safe_zip(raw) as z:
        f=pd.read_parquet(io.BytesIO(z.read("market/raw/yfinance/yf_smh.parquet")))
    idx=pd.to_datetime(f["timestamp"],utc=True,errors="raise").dt.tz_localize(None).dt.normalize()
    f=f[["open","close"]].apply(pd.to_numeric,errors="raise")
    f.index=idx
    f=f.sort_index()
    require(not f.index.has_duplicates and str(f.index[-1].date())==last,
            "FACTOR_SMH_CALENDAR")
    return f


def factors(p,frames,smh,dates):
    # Fixed restricted cohort; no IONQ/COIN/MSTR/QLD in the MOM proxy.
    uni=sorted(set(p["universe"])-set(p["excluded_16"]))
    require(len(uni)==16,"FACTOR_UNIVERSE")
    ix=frames["SPY"].index
    cl=pd.DataFrame({s:frames[s]["close"] for s in uni},index=ix)
    op=pd.DataFrame({s:frames[s]["open"] for s in uni},index=ix)
    cl["SMH"],op["SMH"]=smh.close,smh.open
    ds=pd.to_datetime(dates)
    prev=cl.shift(1)
    rank=cl[uni].pct_change(20,fill_method=None).shift(1).loc[ds]
    require(np.isfinite(rank.to_numpy()).all(),"FACTOR_RANK_MISSING")
    order=np.argsort(-rank.to_numpy(),axis=1,kind="stable")
    def build(f):
        f=f.loc[ds]
        require(np.isfinite(f.to_numpy()).all(),"FACTOR_MISSING")
        v=f[uni].to_numpy()
        ranked=np.take_along_axis(v,order,axis=1)
        mom=ranked[:,:5].mean(1)-ranked[:,-5:].mean(1)
        return np.column_stack([f.SPY,f.QQQ-f.SPY,f.SMH-f.QQQ,f.IWM-f.SPY,mom])
    return build(cl/prev-1),build(op/prev-1),build(cl/op-1)


def fit(y,f):
    x=np.column_stack([np.ones(len(y)),f])
    b,_,rank,_=np.linalg.lstsq(x,y,rcond=None)
    require(rank==x.shape[1],"FACTOR_RANK_DEFICIENT")
    return x,b,y-x@b,np.linalg.inv(x.T@x)


def hac(x,b,e,inv,lag):
    z=x*e[:,None]
    s=z.T@z
    for k in range(1,lag+1):
        a=z[k:].T@z[:-k]
        s+=(1-k/(lag+1))*(a+a.T)
    cov=inv@s@inv
    se=math.sqrt(max(float(cov[0,0]),0))
    require(se>0,"FACTOR_HAC_DEGENERATE")
    return math.erfc(abs(b[0]/se)/math.sqrt(2)),se


def bootstrap(x,y,b,block,reps=REPS):
    # Sufficient statistics for exact OLS refits of joint circular pairs.
    n,k=x.shape
    require(n>=block and reps>=200,"FACTOR_BOOT_SETTINGS")
    z=np.column_stack([(x[:,:,None]*x[:,None,:]).reshape(n,k*k),x*y[:,None]])
    ext=np.vstack([z,z[:block]])
    cs=np.vstack([np.zeros(z.shape[1]),np.cumsum(ext,axis=0)])
    full=cs[block:block+n]-cs[:n]
    rem=n%block
    tail=cs[rem:rem+n]-cs[:n] if rem else None
    rng=np.random.default_rng(SEED+10007*block)
    draws=[]
    for start in range(0,reps,256):
        m=min(256,reps-start)
        idx=rng.integers(0,n,size=(m,n//block+bool(rem)))
        s=full[idx[:,:n//block]].sum(1)
        if rem:
            s+=tail[idx[:,-1]]
        a=s[:,:k*k].reshape(m,k,k)
        v=s[:,k*k:]
        require((np.linalg.matrix_rank(a)==k).all(),"FACTOR_BOOT_RANK")
        draws.extend(np.linalg.solve(a,v[:,:,None])[:,0,0])
    delta=np.asarray(draws)-b[0]
    p=(1+np.sum(np.abs(delta)>=abs(b[0])))/(reps+1)
    ci=b[0]-np.quantile(delta,[.975,.025])
    return float(p),ci


def accounting(stock):
    pnl=defaultdict(float)
    groups=defaultdict(lambda:dict(trades=0,pnl=0.,gross_profit=0.,gross_loss=0.))
    for (_,symbol),v in stock["exit_net_pnl"].items():
        pnl[symbol]+=v
        g=groups[GROUP[symbol]]
        g["trades"]+=1
        g["pnl"]+=v
        g["gross_profit"]+=max(v,0)
        g["gross_loss"]+=min(v,0)
    net=sum(pnl.values())
    require(abs(net-(stock["equity"][-1]-100000))<1e-6 and net>0,
            "FACTOR_PNL_RECONCILE")
    ordered=sorted(pnl.items(),key=lambda x:(-x[1],x[0]))
    return dict(groups=dict(groups),symbol_pnl=dict(ordered),net_pnl=net,
                top3_net_share=sum(x[1] for x in ordered[:3])/net,
                net_without_top3=sum(x[1] for x in ordered[3:]))


def analyze(p,frames,smh,last,ref):
    dates,stocks,_=replay(p,frames,last)
    require(len(dates)==727 and last=="2026-11-23","FACTOR_FROZEN_WINDOW")
    f,on,day=factors(p,frames,smh,dates)
    years=np.asarray([d[:4] for d in dates])
    results={}
    tests=[]
    for name,stock in stocks.items():
        y=daily_return(stock["equity"])
        st=stats(stock["equity"],dates)
        base=ref["scenarios"][name]
        require(abs(st["total_return"]-base["total_return"])<1e-10
                and abs(st["eod_mdd"]-base["eod_mdd"])<1e-10
                and stock["trades"]==base["trades"],"FACTOR_LEDGER_PARITY")
        w=np.asarray(stock["open_weights"])
        cw=np.r_[0.,stock["close_weights"][:-1]]
        adj=on*cw[:,None]+day*w[:,None]
        models={"MKT":f[:,:1],"M4":f[:,:4],"M5":f,"EXPOSURE_M5":adj}
        scenario=name.removesuffix("_K1+K3")
        rows={}
        results[scenario]=rows
        for model,features in models.items():
            x,b,e,inv=fit(y,features)
            names=FACTORS[:features.shape[1]]
            contrib=b[1:]*features.mean(0)
            require(abs(y.mean()-b[0]-contrib.sum())<1e-12,"FACTOR_MEAN_RECONCILE")
            row=dict(alpha_bp_day=float(b[0]*10000),
                     alpha_annual_arith_pct=float(b[0]*25200),
                     annual_mean_pct=float(y.mean()*25200),
                     factor_contributions_annual_pct=dict(zip(names,map(float,contrib*25200))),
                     beta=dict(zip(names,map(float,b[1:]))),
                     r2=float(1-e@e/np.sum((y-y.mean())**2)),
                     condition_number=float(np.linalg.cond(features/features.std(0))),
                     year_alpha_annual_pct={},prior_fit_residual_annual_pct={})
            for year in ("2024","2025","2026"):
                mask=years==year
                row["year_alpha_annual_pct"][year]=float((y[mask]-features[mask]@b[1:]).mean()*25200)
                train=years<year
                if train.any():
                    _,bb,_,_=fit(y[train],features[train])
                    row["prior_fit_residual_annual_pct"][year]=float((y[mask]-features[mask]@bb[1:]).mean()*25200)
            rows[model]=row
            for block in BLOCKS:
                hp,se=hac(x,b,e,inv,block)
                prob,ci=bootstrap(x,y,b,block)
                tests.append(dict(scenario=scenario,model=model,block=block,
                    bootstrap_p=prob,ci_low_bp_day=float(ci[0]*10000),
                    ci_high_bp_day=float(ci[1]*10000),hac_p=hp,
                    hac_ci_low_bp_day=float((b[0]-1.96*se)*10000),
                    hac_ci_high_bp_day=float((b[0]+1.96*se)*10000)))
        rows["accounting"]=accounting(stock)
    for block in BLOCKS:
        selected=[r for r in tests if r["block"]==block]
        require(len(selected)==16,"FACTOR_FAMILY_COUNT")
        for row,pv,hv in zip(selected,holm([r["bootstrap_p"] for r in selected]),
                             holm([r["hac_p"] for r in selected])):
            row.update(bootstrap_holm=float(pv),hac_holm=float(hv))
    return dict(version="kalman-challenger-factor-proxy-v1",
        status="RETROSPECTIVE_RESEARCH_HOLD",research_only=True,approved_live=False,
        source_finality_certified=False,forward_signals_created=0,zero_cash_rate=True,
        first_session=dates[0],last_session=dates[-1],sessions=len(dates),
        factors=list(FACTORS),results=results,significance=tests,
        limitations=["ETF spreads and 16-name lagged MOM20 are proxies, not official Fama-French factors.",
            "Exposure model uses realized opening and preceding close gross weights; intraday exit timing is unknown.",
            "Annualized intercept and contribution are arithmetic, not compounded.",
            "Prior-year fit is a chronological diagnostic on previously studied history, not independent forward validation.",
            "Pairs bootstrap refits the model, not the strategy; Holm covers 16 hypotheses per block only.",
            "Accounting removal is not a counterfactual portfolio rerun. No execution or source finality certification."])


def self_test():
    rng=np.random.default_rng(22)
    f=rng.normal(0,.01,(300,5))
    y=.0003+f@np.array([.3,.1,-.2,.4,.05])+rng.normal(0,.002,300)
    x,b,e,inv=fit(y,f)
    require(abs(b[0]+b[1:]@f.mean(0)-y.mean())<1e-12,"FACTOR_TEST_RECONCILE")
    hp,se=hac(x,b,e,inv,20)
    a=bootstrap(x,y,b,20,256)
    c=bootstrap(x,y,b,20,256)
    require(0<=hp<=1 and se>0 and 0<=a[0]<=1 and a[0]==c[0]
            and np.array_equal(a[1],c[1]),"FACTOR_TEST_STATS")
    # Exact OLS benchmark for a known synthetic linear relationship.
    _,exact,_,_=fit(.001+f@np.arange(5.),f)
    require(np.allclose(exact,np.r_[.001,np.arange(5.)],atol=1e-12),"FACTOR_TEST_OLS")
    stock=dict(exit_net_pnl={("s","AAPL"):10.,("s","AMD"):-2.},
               equity=np.array([100008.]))
    require(accounting(stock)["net_pnl"]==8.,"FACTOR_TEST_ACCOUNTING")
    print("CHALLENGER_FACTOR_PROXY_SYNTHETIC_PASS")


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
            "FACTOR_INPUTS")
    p,h=load_protocol()
    raw=pinned(args.data,args.data_sha256)
    last,frames=archive_frames(p,raw,pinned(args.research,args.research_sha256))
    ref=json.loads(Path(args.reference).read_text())
    require(ref["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD" and ref["protocol_sha256"]==h
            and ref["source_data_sha256"]==args.data_sha256 and
            ref["source_research_sha256"]==args.research_sha256,"FACTOR_REFERENCE_SCOPE")
    result=analyze(p,frames,smh_frame(raw,last),last,ref)
    result.update(protocol_sha256=h,source_data_sha256=args.data_sha256,
                  source_research_sha256=args.research_sha256)
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as fh:
        json.dump(result,fh,indent=2,allow_nan=False)
    print(json.dumps(dict(status=result["status"],sessions=result["sessions"],
                          alpha={s:{m:r["alpha_annual_arith_pct"] for m,r in x.items()
                                   if m!="accounting"} for s,x in result["results"].items()},
                          holm_pass={k:sum(r["bootstrap_holm"]<.05 for r in result["significance"]
                                           if r["block"]==k) for k in BLOCKS})))

if __name__=="__main__":
    main()
