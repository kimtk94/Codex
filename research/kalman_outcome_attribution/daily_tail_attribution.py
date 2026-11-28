"""Fixed historical tail attribution; clipped returns are diagnostics only."""
from __future__ import annotations
import numpy as np
import pandas as pd

COSTS=(20,40,80)
CAPS=(.05,.10,.20)
BUCKETS=("LOSS_GE10","LOSS_5_TO_10","LOSS_LT5","ZERO","WIN_LT5","WIN_5_TO_10","WIN_GE10")


def tail_mean(values,fraction=.10,upper=False):
    """Mean of the worst/best fraction, fractional weight at boundary."""
    if not 0<fraction<=1 or not len(values):
        raise ValueError("INVALID_TAIL_FRACTION_OR_EMPTY")
    a=np.sort(np.asarray(values,dtype=float))
    if not np.isfinite(a).all():
        raise ValueError("INVALID_TAIL_LABEL")
    if upper:a=a[::-1]
    mass=len(a)*fraction
    k=int(np.floor(mass));rem=mass-k
    total=a[:k].sum()+(rem*a[k] if rem>0 and k<len(a) else 0.)
    return float(total/mass)


def bucketize(net):
    return pd.Series(np.select([net.le(-.10),net.le(-.05),net.lt(0),net.eq(0),net.lt(.05),net.lt(.10)],BUCKETS[:-1],default=BUCKETS[-1]),index=net.index)


def describe(g):
    y=g.net
    if not len(y):
        return {"n":0,"mean":None,"median":None,"quantiles":None,"tail10_lower":None,"tail10_upper":None,"buckets":None}
    if not np.isfinite(y).all():raise ValueError("INVALID_OUTCOME")
    lab=bucketize(y)
    bins={}
    for name in BUCKETS:
        a=y.loc[lab.eq(name)]
        bins[name]={"n":len(a),"fraction":float(len(a)/len(y)),"conditional_mean":float(a.mean()) if len(a) else None,
                    "unconditional_mean_contribution":float(a.sum()/len(y))}
    if not np.isclose(sum(b['unconditional_mean_contribution'] for b in bins.values()),y.mean(),atol=1e-12,rtol=0):
        raise ValueError("TAIL_CONTRIBUTION_NOT_CONSERVED")
    return {"n":len(y),"dates":int(g.signal_date.nunique()),"mean":float(y.mean()),"median":float(y.median()),
            "quantiles":{str(v):float(y.quantile(v)) for v in (.05,.10,.25,.50,.75,.90,.95)},
            "tail10_lower":tail_mean(y),"tail10_upper":tail_mean(y,upper=True),"buckets":bins,
            "positive_10_share_of_positive_return_sum":float(y[y.ge(.1)].sum()/y[y.gt(0)].sum()) if y.gt(0).any() else None,
            "negative_10_share_of_negative_return_sum":float(y[y.le(-.1)].sum()/y[y.lt(0)].sum()) if y.lt(0).any() else None}


def group_deltas(g,keys,col):
    means=g.groupby([*keys,"qualifies"])[col].mean().unstack("qualifies")
    if not {False,True}.issubset(means.columns):return pd.Series(dtype=float)
    return (means[True]-means[False]).dropna()


def episode_deltas(g,col):
    means=g.groupby(["episode","qualifies","signal_date"])[col].mean().groupby(level=[0,1]).mean().unstack("qualifies")
    if not {False,True}.issubset(means.columns):return pd.Series(dtype=float)
    return (means[True]-means[False]).dropna()


def contrast(g,family,col):
    a=g.loc[g.qualifies,col];b=g.loc[~g.qualifies,col]
    v=group_deltas(g,["signal_date"],col) if family=="BULL" else episode_deltas(g,col)
    sy=group_deltas(g,["symbol","year"],col)
    return {"pooled":float(a.mean()-b.mean()) if len(a) and len(b) else None,
            "equal_matched_date_or_episode":float(v.mean()) if len(v) else None,"matched_groups":len(v),
            "equal_symbol_year":float(sy.mean()) if len(sy) else None,"symbol_year_groups":len(sy)}


def decompose(a,b):
    """Exact symmetric frequency/magnitude decomposition; empty means unidentified."""
    if not a['n'] or not b['n']:return None
    out={}
    for k in BUCKETS:
        aa,bb=a['buckets'][k],b['buckets'][k]
        pa,pb=aa['fraction'],bb['fraction'];ma,mb=aa['conditional_mean'],bb['conditional_mean']
        observed_both=ma is not None and mb is not None
        ma=ma if ma is not None else mb if mb is not None else 0.
        mb=mb if mb is not None else ma
        freq=(pa-pb)*(ma+mb)/2;size=(pa+pb)*(ma-mb)/2
        out[k]={"total":float(freq+size),"frequency_component":float(freq) if observed_both else None,"conditional_magnitude_component":float(size) if observed_both else None,"both_conditional_means_observed":observed_both}
    if not np.isclose(sum(x['total'] for x in out.values()),a['mean']-b['mean'],atol=1e-12,rtol=0):raise ValueError("DECOMPOSITION_NOT_CONSERVED")
    return out


def analyze(frame,family):
    if family not in ("BULL","BEAR"):raise ValueError("UNKNOWN_FAMILY")
    x=frame.copy()
    if x.duplicated(["symbol","signal_date"]).any() or x.qualifies.isna().any() or not x.qualifies.isin([True,False]).all() or not np.isfinite(x.gross_return).all() or x.gross_return.le(-1).any():raise ValueError("INVALID_CANDIDATE_PANEL")
    x['qualifies']=x.qualifies.astype(bool);x['year']=x.signal_date.str[:4]
    if family=='BEAR' and (x.episode.isna().any() or x.groupby('signal_date').qualifies.nunique().gt(1).any()):raise ValueError("INVALID_BEAR_EPISODE_OR_COMMON_GATE")
    results={}
    for cost in COSTS:
        g=x.copy();g['net']=g.gross_return-cost/10000.
        a,b=(describe(g.loc[g.qualifies.eq(k)]) for k in (True,False))
        row={"qualifying":a,"complement":b,"raw_contrast":contrast(g,family,'net'),"bucket_decomposition":decompose(a,b),"clipped_contrasts":{}}
        for cap in CAPS:
            g['clipped']=g.net.clip(-cap,cap)
            row['clipped_contrasts'][str(cap)]={**contrast(g,family,'clipped'),"qualifying_mean":float(g.loc[g.qualifies,'clipped'].mean()) if g.qualifies.any() else None,"complement_mean":float(g.loc[~g.qualifies,'clipped'].mean()) if (~g.qualifies).any() else None}
        if cost==20:
            row['annual']={str(k):contrast(v,family,'net') for k,v in g.groupby('year')}
            row['leave_one_symbol_out']={str(s):contrast(g.loc[g.symbol.ne(s)],family,'net') for s in sorted(g.symbol.unique())}
            row['omit_semiconductors']=contrast(g.loc[~g.symbol.isin({'NVDA','AMD','AVGO','MU'})],family,'net')
            if family=='BEAR':row['leave_one_episode_out']={str(k):contrast(g.loc[g.episode.ne(k)],family,'net') for k in sorted(g.episode.unique())}
        results[str(cost)]=row
    return {"schema":"kalman-all-daily-tail-attribution-v1","family":family,"research_only":True,"new_holdout":False,"primary_study_admitted_outcomes":0,"approved_live":False,"production_writes":False,"costs":results,
            "limitations":["Previously inspected overlapping labels, not executable trades.","Fixed symmetric clipping is sensitivity only, not attainable stop/target execution.","Tail contribution uses each entire group's observation count; conditional-tail magnitudes are not independent evidence.","No parameter selection or change to registered hypotheses."]}
