"""Joint historical block resampling of archived strategies and matched exposure ETFs.

No new trades, prices, threshold selection, or prospective probabilities.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, ASOF, load_archive
from risk_pilot import read
from exposure_benchmark import benchmark

SCENARIOS = ("BEAR_LOGISTIC_ONLY__ALL_20__POS5__COST20BP",
             "BULL_PLUS_BEAR_LOGISTIC__EXCLUDE_HIGH_RISK__POS5__COST20BP")
BLOCKS = (5,20,60)
REPETITIONS = 10000
SEED = 2601121

def joint_indices(rng, dates, block, size, stratify):
    dates=pd.DatetimeIndex(dates)
    if not len(dates) or not dates.is_unique or not dates.is_monotonic_increasing or min(block,size)<1:
        raise ValueError("INVALID_MC_CALENDAR_OR_SETTINGS")
    parts=[np.flatnonzero(dates.year==y) for y in sorted(set(dates.year))] if stratify else [np.arange(len(dates))]
    out=[]
    for part in parts:
        n=len(part); b=min(block,n)
        starts=rng.integers(0,n,size=(size,(n+b-1)//b))
        out.append(part[((starts[:,:,None]+np.arange(b))%n).reshape(size,-1)[:,:n]])
    return np.concatenate(out,axis=1)

def path_metrics(returns):
    if returns.ndim!=3 or not np.isfinite(returns).all() or (returns<=-1).any():
        raise ValueError("INVALID_MC_RETURNS")
    wealth=np.cumprod(1+returns,axis=1)
    peak=np.maximum.accumulate(np.maximum(wealth,1),axis=1)
    return wealth[:,-1,:]-1,(wealth/peak-1).min(axis=1)

def simulate(values,dates,block,stratify,repetitions=REPETITIONS):
    if values.shape!=(len(dates),6) or repetitions<1:
        raise ValueError("INVALID_MC_DIMENSIONS")
    rng=np.random.default_rng(SEED+block*10007)
    finals=[];drawdowns=[]
    for offset in range(0,repetitions,128):
        ix=joint_indices(rng,dates,block,min(128,repetitions-offset),stratify)
        f,d=path_metrics(values[ix])
        finals.append(f);drawdowns.append(d)
    f=np.concatenate(finals);d=np.concatenate(drawdowns)
    rows=[]
    for i,name in zip((0,3),SCENARIOS):
        x=f[:,i]
        rows.append({"scenario":name,"return_p05_p50_p95":np.quantile(x,[.05,.5,.95]).tolist(),
                     "loss_fraction":float((x<0).mean()),"mdd_p05":float(np.quantile(d[:,i],.05)),
                     "mdd_ge20_fraction":float((d[:,i]<=-.2).mean()),
                     "benchmarks":{s:{"underperform_fraction":float((x<f[:,j]).mean()),
                          "excess_p05_p50_p95":np.quantile(x-f[:,j],[.05,.5,.95]).tolist()}
                         for s,j in zip(("SPY","QQQ"),(i+1,i+2))}})
    return {"block_sessions":block,"stratified_year":stratify,"draws":repetitions,"scenarios":rows}

def run(payload):
    curves=read(payload,"research/regime_challenger/regime_daily_equity.csv")
    dates=None;values=[];closes={}
    for s in ("SPY","QQQ"):
        a=read(payload,"research/factor_lineage/"+s.lower()+".csv.gz")
        if a.session.duplicated().any():
            raise ValueError("DUPLICATE_BENCHMARK_DATE")
        closes[s]=a.set_index("session").daily20_adjusted_close.astype(float)
    for name in SCENARIOS:
        f=curves.loc[curves.scenario.eq(name)].sort_values("date").set_index("date")
        if len(f)!=727 or not f.index.is_unique or str(f.index[-1])!=ASOF:
            raise ValueError("FROZEN_CALENDAR_COVERAGE")
        if dates is None:
            dates=f.index
        if not dates.equals(f.index) or not np.allclose((1+f.daily_return).cumprod()*100000,
                                                       f.equity,atol=1e-5,rtol=0):
            raise ValueError("FROZEN_LEDGER_MISMATCH")
        values.append(f.daily_return.to_numpy())
        for c in closes.values():
            p=c.reindex(dates)
            if not np.isfinite(p).all() or not p.gt(0).all():
                raise ValueError("MISSING_BENCHMARK_CLOSE")
            r=p.pct_change(fill_method=None);r.iloc[0]=0
            values.append(benchmark(r,f.gross_exposure,0)[0].to_numpy())
    v=np.column_stack(values)
    return {"schema":"kalman-paired-exposure-monte-carlo-v1","research_only":True,
            "approved_live":False,"new_holdout":False,"production_writes":False,
            "source_finality_certified":False,"asof":ASOF,"sessions":len(dates),
            "source_sha256":ARCHIVES["results"][2],"seed":SEED,
            "configurations":[simulate(v,dates,b,s) for s in (True,False) for b in BLOCKS],
            "limitations":["Historical observed daily returns resampled; no path-dependent book re-execution.",
                           "Previously inspected strategies; no independent validation or predictive probabilities.",
                           "Zero-cost ETF close-return benchmark with prior-close exposure; intraday mismatch remains.",
                           "Sparse Bear episodes and fixed universe; unobserved crises not represented."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();r=run(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print("PAIRED_EXPOSURE_MONTE_CARLO_RESEARCH_ONLY",len(r["configurations"]),REPETITIONS)

if __name__=="__main__":
    main()
