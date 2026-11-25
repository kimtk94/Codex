"""Historical feasibility diagnostic for the fixed #1078 study protocol.

The source is the already inspected nonoverlapping candidate ledger, NOT
the prospective daily first-sealed score stream. No protocol change,
sample-size optimization, new holdout, or inferential claim.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, load_archive
from risk_pilot import read

HIGH_RISK={"QLD","IONQ","COIN","MSTR"}
VIX_CATEGORIES={"VIX_LT20","VIX_20_30","VIX_GE30","UNKNOWN"}


def compare(g):
    a,b=g.loc[g.qualifies],g.loc[~g.qualifies]
    ga,gb=a.groupby("signal_date").net_return.mean(),b.groupby("signal_date").net_return.mean()
    diff=(ga-gb).dropna()
    return {"rows":len(g),"dates":g.signal_date.nunique(),"qualifying":len(a),
        "complement":len(b),"qualifying_dates":len(ga),"complement_dates":len(gb),
        "matched_dates":len(diff),
        "qualifying_mean":float(a.net_return.mean()) if len(a) else None,
        "complement_mean":float(b.net_return.mean()) if len(b) else None,
        "matched_date_mean_difference":float(diff.mean()) if len(diff) else None,
        "equal_date_group_difference":float(ga.mean()-gb.mean()) if len(ga) and len(gb) else None}


def bear_episodes(context):
    bear=context.regime_lagged.eq("BEAR")
    ids=bear.ne(bear.shift()).cumsum()
    episodes={int(k):(g.index[0],g.index[-1],len(g))
              for k,g in context.loc[bear].groupby(ids[bear])}
    return ids,episodes


def panel(payload):
    bull=read(payload,"research/oos_trades.csv")
    bear=read(payload,"research/regime_challenger/bear_oos_trades.csv")
    ctx=read(payload,"research/regime_challenger/regime_session_context.csv").set_index("date")
    if (len(ctx)!=727 or not ctx.index.is_unique or not ctx.index.is_monotonic_increasing
            or set(ctx.volatility_lagged.unique())!=VIX_CATEGORIES):
        raise ValueError("FROZEN_CONTEXT_MISMATCH")
    bull=bull.loc[bull.strategy.eq("LOGISTIC")].copy()
    bear=bear.loc[bear.candidate_family.eq("BEAR_LOGISTIC")].copy()
    if len(bull)!=439 or len(bear)!=89:
        raise ValueError("CANDIDATE_COUNT_MISMATCH")
    def close(s):
        f=read(payload,"research/factor_lineage/"+s.lower()+".csv.gz")
        q=f.set_index("session").daily20_adjusted_close
        if not q.index.is_unique or not q.index.is_monotonic_increasing:
            raise ValueError("INVALID_PRICE_HISTORY")
        return q
    bull["ret5"]=np.nan
    for s,g in bull.groupby("symbol"):
        bull.loc[g.index,"ret5"]=close(s).pct_change(5,fill_method=None).reindex(g.signal_date).to_numpy()
    bull["spy5"]=bull.signal_date.map(close("SPY").pct_change(5,fill_method=None).shift(1))
    bear["gld5"]=bear.signal_date.map(close("GLD").pct_change(5,fill_method=None).shift(1))
    bear["vix"]=bear.signal_date.map(ctx.volatility_lagged)
    if not np.isfinite(bull[["ret5","spy5"]]).all().all() or not np.isfinite(bear.gld5).all() or not bear.vix.isin(VIX_CATEGORIES-{"UNKNOWN"}).all():
        raise ValueError("INCOMPLETE_GATE_INPUTS")
    bull["qualifies"]=bull.ret5.lt(0)&bull.spy5.ge(0)
    bear["qualifies"]=bear.vix.isin({"VIX_20_30","VIX_GE30"})&bear.gld5.ge(0)
    if int(bull.qualifies.sum())!=108 or int(bear.qualifies.sum())!=47:
        raise ValueError("FROZEN_GATE_COUNT_MISMATCH")
    ids,episodes=bear_episodes(ctx)
    bear["episode"]=bear.signal_date.map(ids)
    if not bear.episode.isin(episodes).all():
        raise ValueError("BEAR_EVENT_OUTSIDE_EPISODE")
    return bull,bear,ctx,episodes


def rolling_feasibility(bull,bear,calendar,episodes,width=252):
    rows=[]
    for start in range(len(calendar)-width+1):
        lo,hi=calendar[start],calendar[start+width-1]
        a,b=bull.loc[bull.signal_date.between(lo,hi)],bear.loc[bear.signal_date.between(lo,hi)]
        ac,bc=compare(a),compare(b)
        complete=sum(lo<=s<=e<=hi and b.loc[b.episode.eq(k),"qualifies"].nunique()==2
                     for k,(s,e,_) in episodes.items())
        rows.append({"bull_matched_dates":ac["matched_dates"],"bull_qualifying":ac["qualifying"],
            "bull_complement":ac["complement"],"bear_matched_complete_episodes":complete,
            "bear_qualifying":bc["qualifying"],"bear_complement":bc["complement"],
            "bear_qualifying_dates":bc["qualifying_dates"],"bear_complement_dates":bc["complement_dates"]})
    q=pd.DataFrame(rows)
    if q.empty:
        raise ValueError("INSUFFICIENT_CALENDAR")
    h1=q.bull_matched_dates.ge(30)&q.bull_qualifying.ge(50)&q.bull_complement.ge(50)
    h2=q.bear_matched_complete_episodes.ge(8)&q.bear_qualifying.ge(50)&q.bear_complement.ge(50)&q.bear_qualifying_dates.ge(20)&q.bear_complement_dates.ge(20)
    return {"window_sessions":width,"windows":len(q),"metric_maxima":{k:int(v) for k,v in q.max().items()},
            "h1_candidate_minimum_pass_windows":int(h1.sum()),"h2_candidate_minimum_pass_windows":int(h2.sum()),
            "not_actual_prospective_coverage":True}


def paired_date_diagnostic(g,calendar):
    a=g.loc[g.qualifies].groupby("signal_date").net_return.mean()
    b=g.loc[~g.qualifies].groupby("signal_date").net_return.mean()
    v=(a-b).dropna()
    arr=v.reindex(calendar).to_numpy()
    rng=np.random.default_rng(42)
    ranges=[]
    for block in (5,20,60):
        n=len(arr)
        starts=rng.integers(0,n,size=(10000,int(np.ceil(n/block))))
        ix=((starts[:,:,None]+np.arange(block))%n).reshape(10000,-1)[:,:n]
        draws=arr[ix];count=np.isfinite(draws).sum(axis=1);ok=count>0
        mean=np.nansum(draws,axis=1)[ok]/count[ok]
        ranges.append({"block":block,"valid_draws":int(ok.sum()),
            "descriptive_1p25_98p75_percentile":np.quantile(mean,[.0125,.9875]).tolist() if len(mean) else None})
    loo=[float((v.sum()-x)/(len(v)-1)) for x in v] if len(v)>1 else []
    return {"matched_dates":len(v),"mean_difference":float(v.mean()) if len(v) else None,
            "leave_one_date_out_range":[min(loo),max(loo)] if loo else None,
            "descriptive_resampling":ranges}


def run(payload):
    bull,bear,ctx,episodes=panel(payload)
    output={}
    for cohort,excluded in (("PRIMARY16",HIGH_RISK),("ALL20",set())):
        a,b=bull.loc[~bull.symbol.isin(excluded)],bear.loc[~bear.symbol.isin(excluded)]
        ep=[]
        for k,(s,e,n) in episodes.items():
            ep.append({"start":s,"end":e,"sessions":n,**compare(b.loc[b.episode.eq(k)])})
        vals=[e["equal_date_group_difference"] for e in ep if e["equal_date_group_difference"] is not None]
        output[cohort]={"bull":compare(a),"bear":compare(b),
            "annual":{str(y):{"bull":compare(a.loc[a.signal_date.str[:4].eq(str(y))]),
                              "bear":compare(b.loc[b.signal_date.str[:4].eq(str(y))])} for y in (2024,2025,2026)},
            "bear_episodes":ep,"bear_matched_episode_count":len(vals),
            "bear_equal_episode_difference":float(np.mean(vals)) if vals else None,
            "bull_date_diagnostic":paired_date_diagnostic(a,ctx.index),
            "rolling_252_session_feasibility":rolling_feasibility(a,b,ctx.index,episodes)}
    return {"schema":"kalman-preregistered-historical-feasibility-v1",
        "input_sha256":ARCHIVES["results"][2],
        "protocol":"https://github.com/kimtk94/Codex/issues/1078",
        "research_only":True,"approved_live":False,"production_writes":False,
        "new_holdout":False,"primary_study_admitted_outcomes":0,"protocol_changed":False,
        "cohorts":output,
        "limitations":["Historical nonoverlapping candidate ledger is not prospective all-daily signal coverage.",
            "Overlapping 252-session windows are not independent observations or estimates of future feasibility.",
            "Minimum sample criteria are kept unchanged; no power or significance claim.",
            "All historical outcomes were previously inspected; resampling ranges are descriptive only.",
            "Source finality and adjustment/identity evidence remain uncertified."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    report=run(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("HISTORICAL_FEASIBILITY_ONLY",report["cohorts"]["PRIMARY16"]["rolling_252_session_feasibility"])
