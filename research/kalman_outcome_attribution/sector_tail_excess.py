"""Descriptive exact-horizon benchmark and extreme-upside attribution.

Fixed discovery gates, previously inspected daily candidates. No hedge
execution, independent holdout, new study admission or policy change.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SEMI={"NVDA","AMD","AVGO","MU"}
BENCHMARKS=("SPY","QQQ","SMH")
METRICS=("net_return","SPY","QQQ","SMH","ex_SPY","ex_QQQ","ex_SMH","win","severe","large")
PREDICTORS=("ret1","ret5","ret20","sma20_gap","rsi14","natr14","adx14",
            "volume_z20","prob","spy_mom5_lag","smh_relative_lag","vix_lag",
            "gld_mom5_lag","credit_mom5_lag")


def attach(frame,prices):
    q=frame.copy()
    for k in ("signal_date","entry_date","exit_date"):
        q[k]=pd.to_datetime(q[k],errors="raise")
    if q.duplicated(["symbol","signal_date"]).any() or not np.isfinite(q.gross_return).all():
        raise ValueError("INVALID_CANDIDATE_KEYS_OR_LABEL")
    if not q.qualifies.isin([True,False]).all():
        raise ValueError("UNCLASSIFIED_GATE")
    q["qualifies"]=q.qualifies.astype(bool)
    cal=prices["SPY"].index
    if not cal.is_unique or not cal.is_monotonic_increasing:
        raise ValueError("INVALID_BENCHMARK_CALENDAR")
    i=cal.get_indexer(q.signal_date)
    if ((i<0)|(i+4>=len(cal))).any() or not np.array_equal(cal[i+1].values,q.entry_date.values) or not np.array_equal(cal[i+4].values,q.exit_date.values):
        raise ValueError("BENCHMARK_HORIZON_MISMATCH")
    for s in BENCHMARKS:
        b=prices[s]
        if not b.index.is_unique or not b.index.is_monotonic_increasing:
            raise ValueError("INVALID_BENCHMARK_CALENDAR")
        op=b.open.reindex(q.entry_date).to_numpy(float)
        cl=b.close.reindex(q.exit_date).to_numpy(float)
        if not (np.isfinite(op)&np.isfinite(cl)&(op>0)&(cl>0)).all():
            raise ValueError("MISSING_OR_INVALID_BENCHMARK_PRICE")
        q[s]=cl/op-1
        # Equal 20bp cost on asset and reference cancels in the difference.
        q["ex_"+s]=q.gross_return-q[s]
    if not np.allclose(q.net_return,q.gross_return-.002,atol=1e-10,rtol=0):
        raise ValueError("ORIGINAL_LABEL_MISMATCH")
    q["win"]=q.net_return.gt(0).astype(int)
    q["severe"]=q.net_return.le(-.05).astype(int)
    q["large"]=q.net_return.ge(.10).astype(int)
    q["year"]=q.signal_date.dt.year
    return q


def compare(g,keys,episode=False):
    if episode:
        m=g.groupby(["episode","qualifies","signal_date"])[list(METRICS)].mean().groupby(level=[0,1]).mean()
    else:
        m=g.groupby([*keys,"qualifies"])[list(METRICS)].mean()
    if m.empty:
        return pd.DataFrame(columns=METRICS,dtype=float)
    a=m.unstack("qualifies")
    if not {True,False}.issubset(a.columns.get_level_values("qualifies")):
        return pd.DataFrame(columns=METRICS,dtype=float)
    return (a.xs(True,axis=1,level="qualifies")-a.xs(False,axis=1,level="qualifies")).dropna()


def describe(g):
    return {"n":len(g),"dates":int(g.signal_date.nunique()),
            "means":{k:float(g[k].mean()) for k in METRICS} if len(g) else None}


def summary(x):
    return {"matched":len(x),"difference":{k:float(x[k].mean()) for k in METRICS} if len(x) else None}


def rank_auc(g,k):
    q=g[[k,"large"]].replace([np.inf,-np.inf],np.nan).dropna()
    n=int(q.large.sum());m=len(q)-n
    if not n or not m:
        return None,0
    return float((q[k].rank().loc[q.large.eq(1)].sum()-n*(n+1)/2)/(n*m)),n*m


def overlap_cluster_sizes(g):
    # Group overlapping entry-to-exit intervals within each original bear episode.
    sizes=[]
    for _,q in g.groupby("episode"):
        end=None
        for r in q.sort_values("entry_date").itertuples():
            if end is None or r.entry_date>end:
                sizes.append(1);end=r.exit_date
            else:
                sizes[-1]+=1;end=max(end,r.exit_date)
    return sizes


def large_wins(g):
    q=g.loc[g.qualifies].copy()
    a=q.loc[q.large.eq(1)];b=q.loc[q.large.eq(0)]
    result={"large":describe(a),"rest":describe(b),"large_semis":int(a.symbol.isin(SEMI).sum()),
            "rest_semis":int(b.symbol.isin(SEMI).sum()),"symbols":int(a.symbol.nunique()),
            "episodes":int(a.episode.nunique()),"overlap_cluster_sizes":overlap_cluster_sizes(a),
            "largest_day_n":int(a.groupby("signal_date").size().max()) if len(a) else 0,
            "large_by_episode":{str(k):int(v) for k,v in a.groupby("episode").size().items()}}
    profiles={}
    # Outcome-period benchmarks are explanatory ONLY, never predictors.
    for k in PREDICTORS+BENCHMARKS+("ex_SPY","ex_SMH"):
        aa=a[k].replace([np.inf,-np.inf],np.nan).dropna()
        bb=b[k].replace([np.inf,-np.inf],np.nan).dropna()
        auc,n=rank_auc(q,k);strata=[rank_auc(z,k) for _,z in q.groupby(["symbol","episode"])]
        pairs=sum(n for _,n in strata)
        profiles[k]={"large_median":float(aa.median()) if len(aa) else None,
                     "rest_median":float(bb.median()) if len(bb) else None,
                     "pooled_auc":auc,"pooled_pairs":n,
                     "within_symbol_episode_auc":float(sum(v*n for v,n in strata if n)/pairs) if pairs else None,
                     "within_symbol_episode_pairs":pairs,
                     "available_at_signal":k in PREDICTORS}
    result["profiles"]=profiles
    return result


def analyze(frame,family,prices):
    if family not in ("BULL","BEAR"):
        raise ValueError("UNKNOWN_FAMILY")
    g=attach(frame,prices)
    if family=="BEAR" and (g.episode.isna().any() or g.groupby("signal_date").qualifies.nunique().gt(1).any()):
        raise ValueError("INVALID_BEAR_EPISODE_OR_COMMON_GATE")
    out={}
    for name,x in (("all",g),("semiconductor_4",g.loc[g.symbol.isin(SEMI)]),
                   ("other",g.loc[~g.symbol.isin(SEMI)]),("nonSPY",g.loc[g.symbol.ne("SPY")])):
        a=x.loc[x.qualifies];b=x.loc[~x.qualifies]
        d=compare(x,["signal_date"],episode=family=="BEAR")
        out[name]={"qualifying":describe(a),"complement":describe(b),
                   "pooled_difference":{k:float(a[k].mean()-b[k].mean()) for k in METRICS} if len(a) and len(b) else None,
                   "equal_date_or_episode":summary(d),
                   "symbol_year":summary(compare(x,["symbol","year"]))}
        if family=="BEAR":
            out[name]["episode_details"]={str(k):{m:float(v) for m,v in r.items()} for k,r in d.iterrows()}
    if family=="BULL":
        a=compare(g.loc[g.symbol.isin(SEMI)],["signal_date"])
        b=compare(g.loc[~g.symbol.isin(SEMI)],["signal_date"])
        i=a.index.intersection(b.index)
        out["common_matched_dates"]={"semiconductors":summary(a.loc[i]),"other":summary(b.loc[i]),
                                     "interaction":summary(a.loc[i]-b.loc[i])}
    else:
        out["extreme_upside"]=large_wins(g)
    return {"schema":"kalman-exact-horizon-sector-tail-v1","family":family,"research_only":True,
            "approved_live":False,"production_writes":False,"new_holdout":False,
            "primary_study_admitted_outcomes":0,"results":out,
            "limitations":["Overlapping candidate observations, not executed trades.",
                "Actual archived adjusted next-open/fourth-close returns; not exchange-certified.",
                "Benchmark comparison subtracts same-horizon gross reference return with equal cost, not a hedge.",
                "SMH is a proxy for four fixed semiconductor names, not a full sector model.",
                "Outcome-period reference returns are explanatory, never signal predictors.",
                "No independent evidence or change to preregistered protocol #1078."]}
