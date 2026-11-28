"""Reduced-feature risk pilot on the inspected frozen candidate ledger.

No Parquet dependency, network, portfolio replay, model persistence or production
side effects. This is a descriptive chronological comparison, not a new holdout.
Run: python risk_pilot.py --results <pinned results ZIP> --out <metadata JSON>
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from outcome_profile import ASOF, ARCHIVES, load_archive, normalize_keys

FEATURES = (
    "ret1", "ret5", "ret20", "sma20_gap", "sma50_gap", "sma200_gap",
    "vol20", "relative20_spy", "spy_mom5_lag", "qqq_mom5_lag",
    "smh_relative_lag", "credit_mom5_lag", "tlt_mom5_lag", "gld_mom5_lag",
)
COLUMNS = [*FEATURES, "probability"]
MIN_ROWS, MIN_DATES, MIN_CLASS = 100, 30, 20
COST_BP, LOSS_CUTOFF = 20, -.05


def read(payload, name):
    blob = payload[name]
    if name.endswith(".gz"):
        blob = gzip.decompress(blob)
    return pd.read_csv(io.BytesIO(blob))


def features_and_events(payload):
    prices = {}
    for name in payload:
        if (name.startswith("research/factor_lineage/") and name.endswith(".csv.gz")
                and "_repaired" not in name):
            d = read(payload, name)
            c = d.set_index(pd.to_datetime(d.session, errors="raise")).daily20_adjusted_close
            c = c.astype(float).sort_index()
            if not c.index.is_unique:
                raise ValueError("DUPLICATE_PRICE_SESSION")
            prices[Path(name).name.split(".")[0].upper()] = c
    bull = read(payload, "research/oos_trades.csv")
    bull = bull.loc[bull.strategy.eq("LOGISTIC")].assign(family="BULL_LOGISTIC")
    bear = read(payload, "research/regime_challenger/bear_oos_trades.csv")
    bear = bear.loc[bear.candidate_family.eq("BEAR_LOGISTIC")].assign(family="BEAR_LOGISTIC")
    events = normalize_keys(pd.concat([bull, bear.drop(columns="candidate_family")],
                                      ignore_index=True))
    if events.duplicated(["family","symbol","signal_date","entry_date","exit_date"]).any():
        raise ValueError("DUPLICATE_CANDIDATE")
    if events.family.value_counts().to_dict() != {"BULL_LOGISTIC":439,"BEAR_LOGISTIC":89}:
        raise ValueError("CANDIDATE_COUNT_MISMATCH")
    if not np.allclose(events.gross_return-.002, events.net_return, rtol=0, atol=2e-9):
        raise ValueError("LABEL_MISMATCH")
    spy = prices["SPY"]
    context = pd.DataFrame({
        "spy_mom5_lag": spy.pct_change(5,fill_method=None).shift(1),
        "qqq_mom5_lag": prices["QQQ"].pct_change(5,fill_method=None).shift(1),
        "smh_relative_lag": (prices["SMH"]/spy).pct_change(10,fill_method=None).shift(1),
        "credit_mom5_lag": (prices["HYG"]/prices["LQD"]).pct_change(5,fill_method=None).shift(1),
        "tlt_mom5_lag": prices["TLT"].pct_change(5,fill_method=None).shift(1),
        "gld_mom5_lag": prices["GLD"].pct_change(5,fill_method=None).shift(1),
    })
    rows = []
    for symbol, group in events.groupby("symbol"):
        c = prices[symbol]
        x = pd.DataFrame(index=c.index)
        for horizon in (1,5,20):
            x[f"ret{horizon}"] = c.pct_change(horizon,fill_method=None)
        for horizon in (20,50,200):
            x[f"sma{horizon}_gap"] = c/c.rolling(horizon,min_periods=horizon).mean()-1
        x["vol20"] = x.ret1.rolling(20,min_periods=20).std()
        x["relative20_spy"] = (c/spy).pct_change(20,fill_method=None)
        x = x.join(context)
        if not group.signal_date.isin(x.index).all():
            raise ValueError("MISSING_SIGNAL_FEATURES")
        rows.append(pd.concat([group.reset_index(drop=True),
            x.loc[group.signal_date,list(FEATURES)].reset_index(drop=True)],axis=1))
    out = pd.concat(rows,ignore_index=True).sort_values(
        ["signal_date","family","symbol"]).reset_index(drop=True)
    if len(out)!=len(events) or not np.isfinite(out[COLUMNS]).all().all():
        raise ValueError("INCOMPLETE_PILOT_FEATURES")
    return out, spy.index


def annual_split(group, calendar, year):
    """Strict exit-date cutoff, including four extra sessions of separation."""
    first = calendar[calendar>=pd.Timestamp(year,1,1)][0]
    cutoff = calendar[calendar.get_loc(first)-4]
    return (group.loc[group.exit_date.lt(cutoff)].copy(),
            group.loc[group.signal_date.dt.year.eq(year)].copy(),cutoff)


def label(frame):
    return frame.net_return.gt(0), frame.net_return.le(LOSS_CUTOFF)


def admissible(train, test):
    win, severe = label(train)
    return (len(train)>=MIN_ROWS and train.signal_date.nunique()>=MIN_DATES
            and min(win.sum(),(~win).sum(),severe.sum(),(~severe).sum())>=MIN_CLASS
            and len(test)>0)


def logistic(x,y):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    return make_pipeline(StandardScaler(),LogisticRegression(
        C=.2,max_iter=500,random_state=42)).fit(x,y)


def ridge(x,y):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    return make_pipeline(StandardScaler(),Ridge(alpha=20)).fit(x,y)


def classification(y,p):
    from sklearn.metrics import roc_auc_score,brier_score_loss
    return {"auc":float(roc_auc_score(y,p)) if y.nunique()==2 else None,
            "brier":float(brier_score_loss(y,p))}


def regression(y,p):
    from sklearn.metrics import mean_absolute_error,mean_squared_error
    from scipy.stats import spearmanr
    return {"mae":float(mean_absolute_error(y,p)),
            "rmse":float(mean_squared_error(y,p)**.5),
            "spearman":float(spearmanr(y,p).statistic)
            if np.unique(p).size>1 and np.unique(y).size>1 else None}


def group_metrics(frame):
    r = frame.net_return
    return {"n":len(r),"dates":int(frame.signal_date.nunique()),
            "mean":float(r.mean()) if len(r) else None,
            "win":float(r.gt(0).mean()) if len(r) else None,
            "severe":float(r.le(LOSS_CUTOFF).mean()) if len(r) else None}


def fit_fold(train,test):
    x,z = train[COLUMNS],test[COLUMNS]
    win,severe = label(train)
    model_win=logistic(x,win)
    model_loss=logistic(x,severe)
    model_return=ridge(x,train.net_return)
    vol=logistic(train[["vol20"]],severe)
    score=logistic(train[["probability"]],win)
    out=test.copy()
    out["win_prob"]=model_win.predict_proba(z)[:,1]
    out["severe_prob"]=model_loss.predict_proba(z)[:,1]
    out["return_pred"]=model_return.predict(z)
    out["vol_risk"]=vol.predict_proba(test[["vol20"]])[:,1]
    out["score_cal"]=score.predict_proba(test[["probability"]])[:,1]
    out["win_prior"]=win.mean()
    out["severe_prior"]=severe.mean()
    out["return_prior"]=train.net_return.mean()
    symbol=train.assign(severe=severe.astype(int)).groupby("symbol").severe.agg(["sum","count"])
    rates=(symbol["sum"]+10*severe.mean())/(symbol["count"]+10)
    out["symbol_risk"]=out.symbol.map(rates).fillna(severe.mean())
    threshold=float(np.quantile(model_loss.predict_proba(x)[:,1],.8))
    out["flag"]=out.severe_prob.ge(threshold)
    out["vol_flag"]=out.vol_risk.ge(float(np.quantile(vol.predict_proba(train[["vol20"]])[:,1],.8)))
    return out,threshold


def fixed_arms(frame):
    return {"BASELINE": pd.Series(True,index=frame.index),
            "RISK_KEEP": ~frame.flag,
            "VOL_KEEP": ~frame.vol_flag,
            "WIN_KEEP": frame.win_prob.ge(.5),
            "COMBINED_KEEP": frame.win_prob.ge(.5)&~frame.flag,
            "RETURN_POS": frame.return_pred.gt(0)}


def matched_date_random(frame, keep, draws=10000):
    """Match count by signal date, not portfolio exposure; diagnostic only."""
    if not keep.index.equals(frame.index) or not keep.isin([True,False]).all():
        raise ValueError("INVALID_KEEP_MASK")
    if draws<1 or not np.isfinite(frame.net_return).all():
        raise ValueError("INVALID_RANDOM_INPUT")
    rng=np.random.default_rng(42)
    sums=np.zeros(draws);severe=np.zeros(draws);n=0
    for _,g in frame.groupby("signal_date",sort=True):
        k=int(keep.loc[g.index].sum())
        n+=k
        if not k:
            continue
        ix=np.argsort(rng.random((draws,len(g))),axis=1)[:,:k]
        v=g.net_return.to_numpy()[ix]
        sums+=v.sum(axis=1);severe+=(v<=LOSS_CUTOFF).sum(axis=1)
    return {"draws":draws,"matched_candidate_count":n,
            "random_mean_net_quantiles":np.quantile(sums/n,[.025,.5,.975]).tolist() if n else None,
            "random_severe_count_quantiles":np.quantile(severe,[.025,.5,.975]).tolist() if n else None,
            "observed":group_metrics(frame.loc[keep]),
            "not_cash_exposure_matched":True}


def fixed_arm_metrics(frame):
    arms=fixed_arms(frame)
    return {"costs":{str(cost):{name:group_metrics(frame.loc[mask].assign(
                net_return=frame.loc[mask,"gross_return"]-cost/10000.))
                for name,mask in arms.items()} for cost in (20,40,80)},
            "date_count_matched_risk_control":matched_date_random(frame,arms["RISK_KEEP"]),
            "portfolio_mdd_verified":False}


def metrics(frame):
    win,severe=label(frame)
    result={"n":len(frame),"dates":int(frame.signal_date.nunique())}
    for name in ("probability","score_cal","win_prior","win_prob"):
        result[name]=classification(win,frame[name])
    for name in ("severe_prior","severe_prob","vol_risk","symbol_risk"):
        result[name]=classification(severe,frame[name])
    for name in ("return_prior","return_pred"):
        result[name]=regression(frame.net_return,frame[name])
    result["flagged"]=group_metrics(frame.loc[frame.flag])
    result["unflagged"]=group_metrics(frame.loc[~frame.flag])
    result["severe_recall"]=float(frame.loc[severe,"flag"].mean()) if severe.any() else None
    return result


def stratified_flag_differences(frame):
    groups=[]
    for _,g in frame.groupby(["symbol",frame.signal_date.dt.year]):
        a,b=g.loc[g.flag],g.loc[~g.flag]
        if len(a) and len(b):
            groups.append((min(len(a),len(b)),
                a.net_return.le(LOSS_CUTOFF).mean()-b.net_return.le(LOSS_CUTOFF).mean(),
                a.net_return.mean()-b.net_return.mean()))
    if not groups:
        return {"groups":0,"positive_severity_difference":0,
                "weighted_severity_difference":None,"weighted_return_difference":None}
    x=np.array(groups)
    return {"groups":len(groups),"positive_severity_difference":int((x[:,1]>0).sum()),
            "weighted_severity_difference":float(np.average(x[:,1],weights=x[:,0])),
            "weighted_return_difference":float(np.average(x[:,2],weights=x[:,0]))}


def resample_brier(frame,calendar):
    q=frame.copy()
    y=q.net_return.le(LOSS_CUTOFF).astype(float)
    q["delta"]=(y-q.severe_prior)**2-(y-q.severe_prob)**2
    q["delta_vol"]=(y-q.vol_risk)**2-(y-q.severe_prob)**2
    cal=calendar[(calendar>=pd.Timestamp("2025-01-01"))&(calendar<=pd.Timestamp(ASOF))]
    agg=q.groupby("signal_date").agg(n=("delta","size"),delta=("delta","sum"),
            delta_vol=("delta_vol","sum")).reindex(cal,fill_value=0).to_numpy(float)
    rng=np.random.default_rng(42)
    rows=[]
    for block in (5,20,60):
        starts=rng.integers(0,len(cal),size=(10000,int(np.ceil(len(cal)/block))))
        idx=((starts[:,:,None]+np.arange(block))%len(cal)).reshape(10000,-1)[:,:len(cal)]
        sums=agg[idx].sum(axis=1)
        valid=sums[:,0]>0
        v=sums[valid,1:]/sums[valid,0,None]
        rows.append({"block":block,"valid":int(valid.sum()),
            "prior_vs_model_delta_brier_95pct":np.quantile(v[:,0],[.025,.975]).tolist(),
            "vol_vs_model_delta_brier_95pct":np.quantile(v[:,1],[.025,.975]).tolist()})
    return rows


def run(payload):
    events,calendar=features_and_events(payload)
    folds, predictions=[],[]
    for family,g in events.groupby("family"):
        for year in (2025,2026):
            tr,te,cutoff=annual_split(g,calendar,year)
            w,s=label(tr)
            row={"family":family,"year":year,"train_n":len(tr),
                "train_dates":int(tr.signal_date.nunique()),"train_wins":int(w.sum()),
                "train_severe":int(s.sum()),"test_n":len(te),
                "test_dates":int(te.signal_date.nunique()),
                "test_severe":int(te.net_return.le(LOSS_CUTOFF).sum()),
                "purge_cutoff":str(cutoff.date())}
            if admissible(tr,te):
                p,threshold=fit_fold(tr,te)
                predictions.append(p)
                row.update(status="EVALUATED",risk_threshold=threshold,metrics=metrics(p))
            else:
                row["status"]="INSUFFICIENT_TRAINING_EVIDENCE"
            folds.append(row)
    report={"schema":"kalman-reduced-risk-pilot-v1","research_only":True,
        "production_writes":False,"approved_live":False,"new_holdout":False,
        "input_sha256":ARCHIVES["results"][2],"candidate_count":len(events),
        "features":list(FEATURES),"archived_score_used":True,"folds":folds,
        "cost_bp":COST_BP,"severe_loss_cutoff":LOSS_CUTOFF,
        "limitations":["Inspected historical selected candidates; no independent confirmation.",
            "Adjusted-close lineage is not independently point-in-time certified.",
            "Not full original 21-feature matrix; not all candidate/noncandidate scores.",
            "No cash-ledger replay, no model or threshold promotion.",
            "Resampling ranges are descriptive, not confirmatory confidence intervals."]}
    if predictions:
        p=pd.concat(predictions,ignore_index=True)
        # A future additional admitted family must be reported separately, not pooled.
        by_family={}
        for family,g in p.groupby("family"):
            q=g.assign(net_return=g.gross_return-.004)
            by_family[family]={"metrics":metrics(g),
                "40bp_frozen_flags":{"flagged":group_metrics(q.loc[q.flag]),
                    "unflagged":group_metrics(q.loc[~q.flag])},
                "within_symbol_year":stratified_flag_differences(g),
                "fixed_arm_comparison":fixed_arm_metrics(g),
                "block_resampling":resample_brier(g,calendar)}
        report["pooled_by_family"]=by_family
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    report=run(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="folds"},allow_nan=False))


if __name__=="__main__":
    main()
