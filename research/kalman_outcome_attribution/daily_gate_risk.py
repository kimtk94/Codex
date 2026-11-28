"""Descriptive all-daily discovery-gate risk attribution, not a new hypothesis test.

Reuse the already reconstructed original Bull/Bear candidates, immutable
gross labels, and fixed historical discovery conditions. No model fitting,
policy selection, new prospective admission or price/strategy write.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

COSTS = (20,40,80)
METRICS = ("net","win","severe")
PROFILE = ("natr14","rsi14","adx14","ret5","sma20_gap","volume_z20","macd_hist","prob")


def outcomes(frame,cost):
    if cost not in COSTS:
        raise ValueError("UNREGISTERED_COST")
    x=frame.copy()
    if not np.isfinite(x.gross_return).all() or x.gross_return.le(-1).any():
        raise ValueError("INVALID_GROSS_LABEL")
    if x.qualifies.isna().any() or not x.qualifies.isin([True,False]).all():
        raise ValueError("UNCLASSIFIED_GATE")
    x["qualifies"]=x.qualifies.astype(bool)
    x["net"]=x.gross_return-cost/10000.
    x["win"]=x.net.gt(0).astype(int)
    x["severe"]=x.net.le(-.05).astype(int)
    return x


def average(x):
    return float(x.mean()) if len(x) else None


def describe(x):
    return {"n":len(x),"dates":int(x.signal_date.nunique()),
            "wins":int(x.win.sum()),"win_rate":average(x.win),
            "severe":int(x.severe.sum()),"severe_rate":average(x.severe),
            "mean_net":average(x.net),"mean_positive":average(x.loc[x.net.gt(0),"net"]),
            "mean_negative":average(x.loc[x.net.lt(0),"net"])}


def difference(group_means):
    """Both arms must exist inside the same stratum; never impute a missing arm."""
    if group_means.empty:
        return pd.DataFrame(columns=METRICS,dtype=float)
    a=group_means.unstack("qualifies")
    if not {False,True}.issubset(a.columns.get_level_values("qualifies")):
        return pd.DataFrame(columns=METRICS,dtype=float)
    a=a.dropna()
    return pd.DataFrame({k:a[k][True]-a[k][False] for k in METRICS})


def contrasts(x,keys):
    return difference(x.groupby([*keys,"qualifies"])[list(METRICS)].mean())


def summary(v):
    return {"matched_groups":len(v),"qualifying_minus_complement":
            {k:average(v[k]) for k in METRICS} if len(v) else None}


def two_way(x):
    """Descriptive Frisch-Waugh projection, not causal estimation.

    A market-level Bear gate is constant within date. Its residual is zero
    after date fixed effects; return NOT_IDENTIFIED rather than a coefficient.
    """
    if x.empty:
        return {"identified":False,"residual_gate_ss":0.,"coefficients":None}
    d=pd.get_dummies(x[["symbol","signal_date"]].astype(str),dtype=float).to_numpy()
    raw=x[["qualifies",*METRICS]].astype(float).to_numpy()
    r=raw-d@np.linalg.lstsq(d,raw,rcond=None)[0]
    g=r[:,0];ss=float(g@g)
    return {"identified":ss>1e-10,"residual_gate_ss":ss,
            "coefficients":{k:float(v) for k,v in zip(METRICS,g@r[:,1:]/ss)}
                if ss>1e-10 else None}


def block_ranges(v,calendar):
    if v.empty:
        return []
    a=v.reindex(calendar)[list(METRICS)].to_numpy(float)
    rng=np.random.default_rng(42);n=len(a);out=[]
    for block in (5,20,60):
        ix=((rng.integers(0,n,size=(10000,int(np.ceil(n/block))))[:,:,None]
             +np.arange(block))%n).reshape(10000,-1)[:,:n]
        samples=[]
        for chunk in np.array_split(ix,20):
            obs=a[chunk];den=np.isfinite(obs).sum(axis=1)
            valid=(den>0).all(axis=1)
            samples.append(np.nansum(obs,axis=1)[valid]/den[valid])
        draws=np.concatenate(samples)
        out.append({"block_sessions":block,"valid_draws":len(draws),
            "descriptive_1p25_98p75_percentile":
                dict(zip(METRICS,np.quantile(draws,[.0125,.9875],axis=0).T.tolist()))
                if len(draws) else None})
    return out


def rank_auc(x,col):
    q=x[[col,"severe"]].replace([np.inf,-np.inf],np.nan).dropna()
    pos=int(q.severe.sum());neg=len(q)-pos
    if not pos or not neg:
        return None,0
    ranks=q[col].rank(method="average")
    return float((ranks.loc[q.severe.eq(1)].sum()-pos*(pos+1)/2)/(pos*neg)),pos*neg


def profiles(x):
    q=x.copy()
    q["outcome"]=np.select([q.win.eq(1),q.severe.eq(1),q.net.lt(0)],
                          ["WIN","SEVERE","MILD"],default="BREAKEVEN")
    ans={}
    for col in PROFILE:
        v=q[col].replace([np.inf,-np.inf],np.nan)
        med=v.groupby(q.outcome).median().dropna()
        auc,pairs=rank_auc(q,col)
        strata=[rank_auc(g,col) for _,g in q.groupby(["symbol","year"])]
        n=sum(p for _,p in strata)
        ans[col]={"outcome_medians":{str(k):float(z) for k,z in med.items()},
                  "pooled_severe_auc":auc,"pooled_pairs":pairs,
                  "within_symbol_year_severe_auc":float(sum(a*p for a,p in strata if p)/n) if n else None,
                  "within_symbol_year_pairs":n,"comparable_strata":sum(p>0 for _,p in strata)}
    return ans


def analyze(frame,family,calendar):
    if family not in ("BULL","BEAR"):
        raise ValueError("UNKNOWN_FAMILY")
    x=frame.copy()
    if x.duplicated(["symbol","signal_date"]).any() or not x.signal_date.isin(calendar).all():
        raise ValueError("INVALID_DAILY_CANDIDATE_KEY")
    x["year"]=x.signal_date.str[:4]
    cost_reports={}
    for cost in COSTS:
        q=outcomes(x,cost)
        date=contrasts(q,["signal_date"])
        v={"qualifies":describe(q.loc[q.qualifies]),"complement":describe(q.loc[~q.qualifies]),
           "same_date":summary(date),"same_symbol_year":summary(contrasts(q,["symbol","year"]))}
        if family=="BEAR":
            if q.groupby("signal_date").qualifies.nunique().gt(1).any():
                raise ValueError("BEAR_GATE_NOT_COMMON_BY_DATE")
            # Equal-weight dates inside each gate and then equal-weight episodes.
            m=q.groupby(["episode","qualifies","signal_date"])[list(METRICS)].mean()
            e=difference(m.groupby(level=["episode","qualifies"]).mean())
            v["equal_episode"]=summary(e)
            v["episode_details"]={str(k):{m:float(z) for m,z in g.items()} for k,g in e.iterrows()}
        if cost==20:
            v["symbol_and_date_fixed_effects"]=two_way(q)
            v["matched_date_descriptive_block_ranges"]=block_ranges(date,calendar)
            v["annual"]={str(y):{"qualifies":describe(g.loc[g.qualifies]),
                "complement":describe(g.loc[~g.qualifies]),
                "same_date":summary(contrasts(g,["signal_date"]))} for y,g in q.groupby("year")}
            v["profiles"]={"qualifies":profiles(q.loc[q.qualifies]),
                           "complement":profiles(q.loc[~q.qualifies])}
        cost_reports[str(cost)]=v
    return {"schema":"kalman-all-daily-gate-risk-v1","family":family,
            "research_only":True,"new_holdout":False,"primary_study_admitted_outcomes":0,
            "approved_live":False,"production_writes":False,"costs":cost_reports,
            "limitations":["Previously inspected overlapping four-session labels, not executed trades.",
                "Fixed effect coefficients are descriptive associations, not causal effects.",
                "Bear gate is common by date and cannot be estimated with date fixed effects.",
                "Date-block ranges and rank AUC comparisons are descriptive, not confirmatory inference.",
                "No threshold tuning, hypothesis promotion or change to preregistration #1078."]}
