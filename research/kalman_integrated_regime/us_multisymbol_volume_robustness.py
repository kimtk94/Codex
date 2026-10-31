#!/usr/bin/env python3
"""Research-only cross-ticker volume robustness (Jan-Oct matched months).

Fits price-only and price+volume on identical all-previous-year training
cohorts for each symbol. Scores a matched Jan-Oct test window in 2025 and
2026 separately. Both models share the SAME test labels/dates per year.

Outputs paired 5-session block-bootstrap CIs for score differences, plus a
TRAIN-prevalence no-skill benchmark. No prices/prints/positions are published.
2025/26 were already explored; bootstrap is descriptive, NOT fresh OOS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
    ARMS, SCREEN_LABELS, build_daily_rows, matched_cohorts,
)


def score(y, p):
    p=np.clip(np.asarray(p,dtype=float),1e-12,1-1e-12)
    y=np.asarray(y,dtype=int)
    return {"brier":float(brier_score_loss(y,p)),
            "logloss":float(log_loss(y,p,labels=[0,1])),
            "auc":float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None}


def paired_block_bootstrap(y, pred_price, pred_volume, *, repeats=400, block=5, seed=1729):
    """Paired resampling preserves common signal dates and short-range correlation."""
    if repeats<100 or block<2 or len(y)<40:
        raise ValueError("INSUFFICIENT_BOOTSTRAP_CONTRACT")
    y=np.asarray(y,dtype=int)
    p=np.asarray(pred_price,dtype=float)
    v=np.asarray(pred_volume,dtype=float)
    if not (len(y)==len(p)==len(v)):
        raise ValueError("BOOTSTRAP_UNPAIRED")
    n=len(y)
    rng=np.random.default_rng(seed)
    stats={"brier":[],"logloss":[],"auc":[]}
    for _ in range(repeats):
        k=int(np.ceil(n/block))
        starts=rng.integers(0,n-block+1,size=k)
        idx=np.concatenate([np.arange(start,start+block) for start in starts])[:n]
        a=score(y[idx],p[idx])
        b=score(y[idx],v[idx])
        for metric in stats:
            if a[metric] is not None and b[metric] is not None:
                stats[metric].append(b[metric]-a[metric])
    intervals={}
    for metric, values in stats.items():
        if len(values)<repeats*.95:
            intervals[metric]={"low":None,"high":None,"valid_replicates":len(values)}
            continue
        intervals[metric]={
            "low":round(float(np.quantile(values,.025)),7),
            "high":round(float(np.quantile(values,.975)),7),
            "valid_replicates":len(values),
        }
    return intervals


def matched_months(year, train, test, *, bootstrap_reps=400):
    """Only test Jan to October for both years; fit to same preyear history."""
    test=test.loc[test.date_ny.dt.month.le(10)].copy()
    if len(test)<120:
        raise ValueError(f"TOO_FEW_MATCHED_MONTHS_{year}:{len(test)}")
    if not test.next_session_date.dt.month.le(10).all():
        raise AssertionError("LABEL_OUTSIDE_MATCHED_MONTHS")
    tr_ret=train.next_session_rth_return.astype(float).to_numpy()
    te_ret=test.next_session_rth_return.astype(float).to_numpy()
    move_cutoff=float(np.quantile(np.abs(tr_ret),.75))
    report={
        "year":year,
        "train_sessions":len(train),
        "test_jan_oct_sessions":len(test),
        "test_first":str(test.date_ny.min().date()),
        "test_last":str(test.date_ny.max().date()),
        "last_prior_year_train_label":str(train.next_session_date.max().date()),
        "outcomes":{}
    }
    for target in SCREEN_LABELS:
        if target=="direction_up":
            ytr=(tr_ret>0).astype(int)
            yte=(te_ret>0).astype(int)
        else:
            ytr=(np.abs(tr_ret)>=move_cutoff).astype(int)
            yte=(np.abs(te_ret)>=move_cutoff).astype(int)
        if len(np.unique(ytr))!=2 or len(np.unique(yte))!=2:
            raise ValueError("OUTCOME_ONE_CLASS:"+str(year)+":"+target)
        predictions={}
        for arm, columns in ARMS.items():
            model=make_pipeline(
                StandardScaler(),
                LogisticRegression(C=1.0,class_weight="balanced",
                                   max_iter=1000,random_state=42))
            model.fit(train[columns],ytr)
            predictions[arm]=model.predict_proba(test[columns])[:,1]
        a=score(yte,predictions["P_price_3"])
        b=score(yte,predictions["V_price_volume_5"])
        baseline=score(yte,np.repeat(ytr.mean(),len(yte)))
        ci=paired_block_bootstrap(
            yte,predictions["P_price_3"],predictions["V_price_volume_5"],
            repeats=bootstrap_reps,block=5,seed=year+31*(target=="next_session_large_move"))
        report["outcomes"][target]={
            "train_label_positive_rate":round(float(ytr.mean()),7),
            "test_label_positive_rate":round(float(yte.mean()),7),
            "move_cutoff_training_only":round(move_cutoff,7) if target=="next_session_large_move" else None,
            "no_skill_train_prevalence":{k:round(v,7) for k,v in baseline.items() if v is not None},
            "price_only":{k:round(v,7) for k,v in a.items() if v is not None},
            "price_plus_volume":{k:round(v,7) for k,v in b.items() if v is not None},
            "volume_minus_price":{k:round(b[k]-a[k],7) for k in a if a[k] is not None and b[k] is not None},
            "paired_five_session_block_bootstrap_95pct":ci,
            "exploratory_many_comparisons":True,
            "volume_inclusion_approved":False
        }
    return report


def run_robustness(bars, *, bootstrap_reps=400):
    daily,qa=build_daily_rows(bars)
    all_results={}
    for symbol,df in daily.groupby("symbol",sort=True):
        yearly={}
        for year in (2025,2026):
            train,test=matched_cohorts(df,year)
            yearly[str(year)]=matched_months(year,train,test,bootstrap_reps=bootstrap_reps)
        all_results[symbol]=yearly
    return {
        "schema":"kalman-us-five-ticker-jan-oct-volume-ablation-blockboot-v1",
        "status":"EXPLORATORY_NO_LIVE_GO",
        "reviewed_years":"2025 and 2026 (not untouched)",
        "matched_months":"Jan-Oct both years; unequal historical training periods remain",
        "target":"next session open-to-close return classification",
        "model_features":ARMS,
        "bootstrap":{"repeats":bootstrap_reps,"block_us_trading_sessions":5,
                     "confidence":.95,"interpretation":"descriptive, exploratory; multiple comparisons unadjusted"},
        "source_quality":qa,
        "by_symbol":all_results,
        "no_live_changes":True,
        "limitations":[
            "Historical data already inspected; confidence intervals do not turn this into untouched OOS.",
            "Signals computed only after RTH close, outcomes next session open-to-close.",
            "No transaction costs, fills, bid/ask slippage or financing; NOT a trading backtest.",
            "Five-ticker × two-label × two-year × multiple-metric comparisons unadjusted.",
            "Market holiday and month-boundary test-day counts may differ slightly year to year.",
            "Class-balanced logistic probabilities are not necessarily calibrated; no-skill training-prevalence benchmark reported.",
            "SIP adjusted bar volume and split consistency require independent data-quality assessment."
        ]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-bars",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--bootstrap-reps",type=int,default=400)
    a=ap.parse_args()
    if not 100<=a.bootstrap_reps<=1000:
        raise SystemExit("INVALID_BOOTSTRAP_REPS")
    results=run_robustness(pd.read_parquet(a.input_bars),bootstrap_reps=a.bootstrap_reps)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(results,indent=2,ensure_ascii=False)+"\n")
    print("US_VOLUME_MATCHED_MONTHS_ROBUSTNESS "+json.dumps({
        "status":results["status"],
        "results":{s:{year:{
            target:{"delta":x["volume_minus_price"],
                    "ci":x["paired_five_session_block_bootstrap_95pct"],
                    "train_base_brier":x["no_skill_train_prevalence"]["brier"]}
            for target,x in y["outcomes"].items()}
            for year,y in result.items()}
            for s,result in results["by_symbol"].items()},
        "live_hold":True},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
