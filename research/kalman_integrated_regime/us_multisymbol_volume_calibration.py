#!/usr/bin/env python3
"""Five-ticker, Jan-Oct prior-only probability calibration and no-skill audit.

No orders, live code, secret exposure or public raw SIP data. Compare:
  (0) constant prior-year TRAIN label event prevalence;
  (1) unweighted logit price-3;
  (2) unweighted logit price-3 + RVOL20 and volume-z20;
  (3) prior class-balanced logit price-3;
  (4) prior class-balanced logit price-3 + volume-2.

Calibrated/untouched is NOT claimed. A class-unweighted logistic fit is a
baseline to test whether class_weight='balanced' made the historical
large-move probabilities unsuitable without calibration.

Signals at T RTH close; next session open-to-close labels at T+1.
Historical 2025 & 2026 have already been reviewed, so no fresh OOS claims.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
    PRICE, VOLUME, SCREEN_LABELS, build_daily_rows, matched_cohorts,
)
from research.kalman_integrated_regime.us_multisymbol_volume_robustness import (
    score, paired_block_bootstrap,
)


ARMS = {
    "P_unweighted": (PRICE, None),
    "V_unweighted": (PRICE + VOLUME, None),
    "P_balanced": (PRICE, "balanced"),
    "V_balanced": (PRICE + VOLUME, "balanced"),
}


def reliability(y, p, bins=10):
    """Equal-width bins; small bins are reported, not concealed."""
    y=np.asarray(y,dtype=int)
    p=np.asarray(p,dtype=float)
    which=np.minimum((p*bins).astype(int),bins-1)
    table=[]
    for i in range(bins):
        flag=(which==i)
        table.append({
            "bin":i,
            "count":int(flag.sum()),
            "mean_probability":round(float(p[flag].mean()),6) if flag.any() else None,
            "observed_frequency":round(float(y[flag].mean()),6) if flag.any() else None,
        })
    ece=sum(float(flag["count"])*
            abs(flag["mean_probability"]-flag["observed_frequency"])
            for flag in table if flag["count"]>0)/len(y)
    return {"equal_width_bin_count":bins,
            "expected_calibration_error":round(ece,7),
            "reliability_bins":table}


def calibrate_annual(train,test,year,bootstrap_reps=400):
    # No label from November should be used in Jan-Oct evaluation.
    test=test.loc[test.date_ny.dt.month.le(10)
                  &test.next_session_date.dt.month.le(10)].copy()
    if len(test)<120 or train.next_session_date.max()>=pd.Timestamp(f"{year}-01-01"):
        raise ValueError("CALIBRATION_COHORT_INVALID")
    tr_ret=train.next_session_rth_return.astype(float).to_numpy()
    te_ret=test.next_session_rth_return.astype(float).to_numpy()
    cutoff=float(np.quantile(np.abs(tr_ret),.75))
    targets={}
    for target in SCREEN_LABELS:
        if target=="direction_up":
            ytr=(tr_ret>0).astype(int)
            yte=(te_ret>0).astype(int)
        else:
            ytr=(np.abs(tr_ret)>=cutoff).astype(int)
            yte=(np.abs(te_ret)>=cutoff).astype(int)
        if len(np.unique(ytr))!=2 or len(np.unique(yte))!=2:
            raise ValueError("ONE_CLASS_BINARY_TARGET")
        base_rate=float(np.mean(ytr))
        actual_rate=float(np.mean(yte))
        results={}
        baseline_p=np.full(len(yte),base_rate,dtype=float)
        baseline=score(yte,baseline_p)
        results["constant_train_prevalence"]={
            "metrics":{k:round(v,7) for k,v in baseline.items() if v is not None},
            "mean_prediction":round(base_rate,7),
            "calibration":reliability(yte,baseline_p)}
        preds={}
        for arm,(cols,weights) in ARMS.items():
            model=make_pipeline(
                StandardScaler(),
                LogisticRegression(
                    C=1.0,max_iter=1000,class_weight=weights,random_state=42
                ),
            )
            model.fit(train[cols],ytr)
            p=model.predict_proba(test[cols])[:,1]
            preds[arm]=p
            result=score(yte,p)
            results[arm]={
                "metrics":{k:round(v,7) for k,v in result.items() if v is not None},
                "features":cols,
                "class_weight":str(weights),
                "mean_prediction":round(float(p.mean()),7),
                "calibration":reliability(yte,p)
            }
        p=results["P_unweighted"]["metrics"]
        v=results["V_unweighted"]["metrics"]
        cp=results["constant_train_prevalence"]["metrics"]
        ci=paired_block_bootstrap(
            yte,preds["P_unweighted"],preds["V_unweighted"],
            repeats=bootstrap_reps,block=5,seed=year+43*(target=="next_session_large_move")
        )
        targets[target]={
            "train_label_prevalence":round(base_rate,7),
            "test_label_prevalence":round(actual_rate,7),
            "training_only_large_move_cutoff":round(cutoff,7) if target=="next_session_large_move" else None,
            "scores":results,
            "unweighted_volume_minus_price":{
                k:round(v[k]-p[k],7) for k in ("brier","logloss","auc")},
            "unweighted_volume_minus_constant":{
                k:round(v[k]-cp[k],7) for k in ("brier","logloss")},
            "unweighted_volume_vs_price_5day_block_95pct":ci,
            "strict_brier_better_than_price_and_constant":
                v["brier"]<p["brier"] and v["brier"]<cp["brier"],
            "strict_logloss_better_than_price_and_constant":
                v["logloss"]<p["logloss"] and v["logloss"]<cp["logloss"],
            "not_live_approved":True,
        }
    return {
        "train":len(train),
        "test_matched_jan_oct":len(test),
        "train_last_known_target_exit":str(train.next_session_date.max().date()),
        "test_window":[str(test.date_ny.min().date()),str(test.date_ny.max().date())],
        "targets":targets,
        "no_future_label_in_training":True,
    }


def run(bars,bootstrap_reps=400):
    daily,qa=build_daily_rows(bars)
    output={}
    for symbol,df in daily.groupby("symbol",sort=True):
        years={}
        for year in (2025,2026):
            tr,te=matched_cohorts(df,year)
            years[str(year)]=calibrate_annual(tr,te,year,bootstrap_reps)
        output[symbol]=years
    return {
        "schema":"kalman-us-five-unweighted-calibration-v1",
        "status":"RESEARCH_PROBABILITY_SCREEN_ONLY",
        "source":"ALPACA_SIP_ADJUSTMENT_ALL_15MIN",
        "source_quality":qa,
        "signal_after":"RTH close",
        "outcome":"next US session open-to-close",
        "test_window":"Jan-Oct for both years, T+1 label also Jan-Oct",
        "arms":{k:{"columns":v[0],"weighting":str(v[1])} for k,v in ARMS.items()},
        "by_symbol":output,
        "bootstrap_reps":bootstrap_reps,
        "live_execution_modified":False,
        "decision":"HOLD",
        "notes":[
            "2025/2026 data have previously been analyzed; future independent data needed.",
            "A confidence interval can be nominal before multiplicity adjustment; no claims of 5x2x2 familywise significance.",
            "Unweighted logit is not guaranteed calibrated; train prevalence and ECE guardrails reported.",
            "A better Brier/logloss alone does NOT establish a profitable trade strategy.",
            "No fills, fees, slippage, MDD, overnight gaps, or actual signed SIP aggressor flow."
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-bars",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--bootstrap-reps",type=int,default=400)
    a=p.parse_args()
    if not 100<=a.bootstrap_reps<=1000:
        raise SystemExit("BOOTSTRAP_REPEAT_INVALID")
    result=run(pd.read_parquet(a.input_bars),bootstrap_reps=a.bootstrap_reps)
    dest=Path(a.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    summary={
        ticker:{
            year:{
                target:{
                    "constant":item["scores"]["constant_train_prevalence"]["metrics"],
                    "unweighted_price":item["scores"]["P_unweighted"]["metrics"],
                    "unweighted_price_volume":item["scores"]["V_unweighted"]["metrics"],
                    "balanced_price_volume":item["scores"]["V_balanced"]["metrics"],
                    "delta":item["unweighted_volume_minus_price"],
                    "vs_constant":item["unweighted_volume_minus_constant"],
                    "passes_baselines":item["strict_brier_better_than_price_and_constant"]
                }
                for target,item in y["targets"].items()}
                for year,y in yr.items()}
                for ticker,yr in result["by_symbol"].items()
    }
    print("FIVE_TICKER_CALIBRATION_SUMMARY "+json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
