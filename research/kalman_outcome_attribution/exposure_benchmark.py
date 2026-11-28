"""Read-only exposure-matched close-return diagnostics on archived equity curves."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, ASOF, load_archive
from risk_pilot import read

def perf(r):
    if not len(r) or not np.isfinite(r).all() or (r<=-1).any():
        raise ValueError("INVALID_RETURN")
    wealth=(1+r).cumprod()
    sd=r.std(ddof=1)
    return {"total_return":float(wealth.iloc[-1]-1),
        "max_drawdown":float((wealth/wealth.cummax().clip(lower=1)-1).min()),
        "sharpe_zero_cash":float(r.mean()/sd*np.sqrt(252)) if sd>0 else None}

def benchmark(r, exposure, one_way_bp=0):
    if not r.index.equals(exposure.index) or not np.isfinite(exposure).all() or not exposure.between(0,1).all():
        raise ValueError("INVALID_EXPOSURE")
    if not np.isfinite(r).all() or (r<=-1).any() or one_way_bp<0:
        raise ValueError("INVALID_BENCHMARK_INPUT")
    w=exposure.shift(1,fill_value=0)
    # Previous holding after price drift, before target reset. Close-only
    # turnover approximation; not a replay of open/close fills.
    prior=w.shift(1,fill_value=0)
    prev_r=r.shift(1,fill_value=0)
    drift=prior*(1+prev_r)/(1+prior*prev_r)
    turnover=(w-drift).abs()
    net=w*r-turnover*one_way_bp/10000
    return net,w,turnover

def compare(g, closes):
    g=g.sort_values("date").set_index("date")
    if not g.index.is_unique or len(g)!=727 or str(g.index[-1])!=ASOF:
        raise ValueError("EQUITY_CALENDAR")
    ret=g.daily_return.astype(float)
    if not np.allclose((1+ret).cumprod()*100000,g.equity,rtol=0,atol=1e-5):
        raise ValueError("EQUITY_RECONCILIATION")
    actual=perf(ret)
    ans={"actual":actual,"benchmarks":{}}
    for s,close in closes.items():
        c=close.reindex(g.index)
        if not np.isfinite(c).all() or not c.gt(0).all():
            raise ValueError("BENCHMARK_CLOSE_COVERAGE")
        r=c.pct_change(fill_method=None);r.iloc[0]=0
        results={}
        for bp in (0,10,20,40):
            b,w,turnover=benchmark(r,g.gross_exposure,bp)
            m=perf(b)
            results[str(bp)]={**m,"excess_total_return":actual["total_return"]-m["total_return"],
                "turnover_sum":float(turnover.sum()),
                "yearly_excess":{str(y):float((1+ret.loc[ix]).prod()-(1+b.loc[ix]).prod())
                    for y,ix in g.groupby(g.index.str[:4]).groups.items()}}
        ans["benchmarks"][s]={"full_hold":perf(r),"mean_lagged_exposure":float(w.mean()),
            "constant_mean_exposure_hindsight_diagnostic":perf(r*w.mean()),
            "lagged_exposure":results}
    return ans

def run(payload):
    closes={}
    for s in ("SPY","QQQ"):
        p=read(payload,"research/factor_lineage/"+s.lower()+".csv.gz")
        if p.session.duplicated().any():
            raise ValueError("DUPLICATE_BENCHMARK_DATE")
        closes[s]=p.set_index("session").daily20_adjusted_close
    curves=pd.concat([read(payload,n) for n in ("research/portfolio_daily_equity.csv",
                  "research/regime_challenger/regime_daily_equity.csv")],ignore_index=True)
    if curves.scenario.nunique()!=36:
        raise ValueError("SCENARIO_COVERAGE")
    rows={name:compare(g,closes) for name,g in curves.groupby("scenario")}
    return {"schema":"kalman-lagged-exposure-v1","research_only":True,"approved_live":False,
        "production_writes":False,"new_holdout":False,"source_finality_certified":False,
        "input_sha256":ARCHIVES["results"][2],"scenario_count":len(rows),"scenarios":rows,
        "limitations":["Previously inspected historical adjusted-price archive.",
        "Lagged close exposure matches only prior close allocation; intraday entry/exit exposure differs.",
        "Trading costs on ETF benchmark are approximate close-rebalancing costs; cash interest zero.",
        "Static mean exposure is a hindsight-only diagnostic; not an implementable historical policy.",
        "No inference of causal alpha, no prospective validation or new cash replay."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();r=run(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print("LAGGED_EXPOSURE_RESEARCH_ONLY",r["scenario_count"])

if __name__=="__main__":
    main()
