"""Separate structural and timing risk on frozen Bull Logistic candidates.

Descriptive expanding-year pilot, no new holdout or trading policy. Reuses
risk_pilot's exact archive checks, candidate labels, and four-session purge.
No row-level data or model weights emitted.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from outcome_profile import ARCHIVES, ASOF, load_archive
from risk_pilot import read, features_and_events, annual_split, admissible, classification

HIGH_RISK = {"QLD", "COIN", "MSTR", "IONQ"}
REL = ("relative_vol", "ret5_own_iqr", "ret20_own_iqr", "gap20_own_iqr")
CONTEXT = ("spy_mom5_lag", "qqq_mom5_lag", "smh_relative_lag",
           "credit_mom5_lag", "gld_mom5_lag", "tlt_mom5_lag")
TIMING = [*REL, *CONTEXT]
MODEL_COLUMNS = {
    "VOL_ABS": ["vol20"], "VOL_REL": ["relative_vol"],
    "TIMING_ONLY": TIMING, "SYMBOL_ONLY": ["symbol"],
    "SYMBOL_REL_VOL": ["symbol", "relative_vol"],
    "SYMBOL_TIMING": ["symbol", *TIMING],
}
METHODS = ["POP_PRIOR", "SYMBOL_PRIOR", *MODEL_COLUMNS]


def relative_features(close):
    """Signal-day values normalized against the preceding 252 observations.
    At least 126 prior valid observations; no future or current normalizer.
    """
    ret = close.pct_change(fill_method=None)
    vol = ret.rolling(20,min_periods=20).std()
    gap = close/close.rolling(20,min_periods=20).mean()-1
    out = pd.DataFrame({"relative_vol":np.log(
        vol/vol.shift(1).rolling(252,min_periods=126).median())})
    for name, series in (("ret5",close.pct_change(5,fill_method=None)),
                         ("ret20",close.pct_change(20,fill_method=None)),("gap20",gap)):
        h = series.shift(1).rolling(252,min_periods=126)
        iqr = (h.quantile(.75)-h.quantile(.25)).replace(0,np.nan)
        out[name+"_own_iqr"] = (series-h.median())/iqr
    return out.replace([np.inf,-np.inf],np.nan)


def prepare(payload):
    events,calendar = features_and_events(payload)
    bull = events.loc[events.family.eq("BULL_LOGISTIC")]
    rows = []
    for symbol,g in bull.groupby("symbol"):
        name = "research/factor_lineage/"+symbol.lower()+".csv.gz"
        d = read(payload,name)
        close = d.set_index(pd.to_datetime(d.session,errors="raise")).daily20_adjusted_close.astype(float).sort_index()
        if not close.index.is_unique or not g.signal_date.isin(close.index).all():
            raise ValueError("MISSING_OR_DUPLICATE_RELATIVE_HISTORY")
        x = relative_features(close).loc[g.signal_date,list(REL)].reset_index(drop=True)
        rows.append(pd.concat([g.reset_index(drop=True),x],axis=1))
    out = pd.concat(rows,ignore_index=True).sort_values(["signal_date","symbol"]).reset_index(drop=True)
    if len(out)!=439 or not np.isfinite(out[[*TIMING,"vol20"]]).all().all():
        raise ValueError("INCOMPLETE_TIMING_FEATURES")
    out["severe"] = out.net_return.le(-.05).astype(int)
    out["year"] = out.signal_date.dt.year
    return out,calendar


def predict_fold(train,test):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.linear_model import LogisticRegression
    out = test.copy()
    prior = train.severe.mean()
    counts = train.groupby("symbol").severe.agg(["sum","count"])
    rates = (counts["sum"]+10*prior)/(counts["count"]+10)
    out["POP_PRIOR"] = prior
    out["SYMBOL_PRIOR"] = out.symbol.map(rates).fillna(prior)
    for method,cols in MODEL_COLUMNS.items():
        numeric = [c for c in cols if c!="symbol"]
        transforms = []
        if "symbol" in cols:
            transforms.append(("symbol",OneHotEncoder(handle_unknown="ignore"),["symbol"]))
        if numeric:
            transforms.append(("numeric",StandardScaler(),numeric))
        estimator = make_pipeline(ColumnTransformer(transforms),
            LogisticRegression(C=.2,max_iter=500,random_state=42))
        estimator.fit(train[cols],train.severe)
        out[method] = estimator.predict_proba(test[cols])[:,1]
    return out


def within_symbol_year(frame,method):
    from sklearn.metrics import roc_auc_score
    pairs,weighted,groups = 0,0.,0
    for _,g in frame.groupby(["symbol","year"]):
        n1 = int(g.severe.sum())
        n0 = len(g)-n1
        if not n1 or not n0:
            continue
        pairs += n1*n0
        weighted += n1*n0*roc_auc_score(g.severe,g[method])
        groups += 1
    return {"auc":weighted/pairs if pairs else None,"pairs":pairs,"groups":groups}


def summary(frame):
    return {"n":len(frame),"dates":int(frame.signal_date.nunique()),
            "severe":int(frame.severe.sum()),"severe_rate":float(frame.severe.mean()),
            "mean_net_return":float(frame.net_return.mean()),
            "metrics":{m:classification(frame.severe,frame[m]) for m in METHODS},
            "within_symbol_year":{m:within_symbol_year(frame,m) for m in METHODS}}


def resample(frame,calendar):
    q = frame.copy()
    comparisons = (("symbol_vs_relative","SYMBOL_ONLY","SYMBOL_REL_VOL"),
                   ("symbol_vs_timing","SYMBOL_ONLY","SYMBOL_TIMING"),
                   ("prior_vs_timing","SYMBOL_PRIOR","SYMBOL_TIMING"))
    for k,a,b in comparisons:
        q[k] = (q.severe-q[a])**2-(q.severe-q[b])**2
    keys = [x[0] for x in comparisons]
    cal = calendar[(calendar>=pd.Timestamp("2025-01-01"))&(calendar<=pd.Timestamp(ASOF))]
    daily = q.groupby("signal_date").agg(n=("severe","size"),
        **{k:(k,"sum") for k in keys}).reindex(cal,fill_value=0).to_numpy(float)
    rng = np.random.default_rng(42)
    rows = []
    n = len(daily)
    for block in (5,20,60):
        starts = rng.integers(0,n,size=(10000,int(np.ceil(n/block))))
        idx = ((starts[:,:,None]+np.arange(block))%n).reshape(10000,-1)[:,:n]
        sums = daily[idx].sum(axis=1)
        valid = sums[:,0]>0
        v = sums[valid,1:]/sums[valid,0,None]
        rows.append({"block":block,"valid":int(valid.sum()),
                     "descriptive_ranges":{k:np.quantile(v[:,i],[.025,.975]).tolist()
                                            for i,k in enumerate(keys)}})
    return rows


def run(payload):
    data,calendar = prepare(payload)
    folds,predictions = [],[]
    for year in (2025,2026):
        tr,te,cutoff = annual_split(data,calendar,year)
        if not admissible(tr,te):
            raise ValueError("INSUFFICIENT_BULL_TRAINING_EVIDENCE")
        out = predict_fold(tr,te)
        predictions.append(out)
        folds.append({"year":year,"train_n":len(tr),"cutoff":str(cutoff.date()),**summary(out)})
    p = pd.concat(predictions,ignore_index=True)
    return {
        "schema":"kalman-structural-timing-risk-v1","input_sha256":ARCHIVES["results"][2],
        "research_only":True,"production_writes":False,"approved_live":False,
        "new_holdout":False,"cost_bp":20,"severe_loss_cutoff":-.05,
        "folds":folds,"pooled":summary(p),
        "fixed_cohorts":{k:summary(g) for k,g in (
            ("HIGH_RISK_4",p.loc[p.symbol.isin(HIGH_RISK)]),
            ("OTHER_16",p.loc[~p.symbol.isin(HIGH_RISK)]))},
        "relative_volatility_groups":{str(k):summary(g) for k,g in p.groupby(p.relative_vol.gt(0))},
        "block_resampling":resample(p,calendar),
        "limitations":[
            "Previously inspected, selected candidates; no new holdout or causal inference.",
            "Adjusted close basis not independently certified; reduced-feature pilot.",
            "Same-symbol/year rank pairs are not independent observations.",
            "Fixed cohort is a sensitivity split, not a proposed exclusion policy.",
            "Block ranges are descriptive, not confirmatory confidence intervals.",
            "No portfolio rerun, threshold tuning or model promotion.",
        ],
    }


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    out=Path(a.out)
    report=run(load_archive(a.results,"results"))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(report["pooled"],allow_nan=False))
