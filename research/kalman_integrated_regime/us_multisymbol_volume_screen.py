#!/usr/bin/env python3
"""Research-only multi-ticker volume ablation: next-session price-direction and move-size.

No trading orders, no position sizing, no live model writes. Use adjusted
Alpaca SIP 15m RTH bars, signal computed only after session close. Compare
price-only P against price + RVOL/zscore V on matched training and test days.

Predictions refer to NEXT session open-to-close return. This is a screening
study, NOT a TP/SL strategy or validated profitability claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime.us_multisymbol_microstructure import (
    symbol_volume_features, NY
)

PRICE = ["price_r5", "price_r20", "price_logvol20"]
VOLUME = ["rvol20", "volume_z20"]
ARMS = {"P_price_3":PRICE, "V_price_volume_5":PRICE+VOLUME}
YEARS = (2025,2026)
SCREEN_LABELS = ("direction_up", "next_session_large_move")


def build_daily_rows(bars:pd.DataFrame)->tuple[pd.DataFrame,dict]:
    vf,qa=symbol_volume_features(bars,lookback=20)
    data=bars.copy()
    data["market"]=data.market.astype(str).str.upper()
    data["ts"]=pd.to_datetime(data.candle_time_utc,utc=True)
    data["date_ny"]=pd.to_datetime(data.ts.dt.tz_convert(NY).dt.strftime("%Y-%m-%d"))
    cal=xcals.get_calendar("XNYS")
    observations=[]
    for (symbol,day),group in data.groupby(["market","date_ny"]):
        if not cal.is_session(day):
            continue
        start=cal.session_open(day)
        end=cal.session_close(day)
        rth=group.loc[group.ts.ge(start)&group.ts.lt(end)].sort_values("ts")
        if rth.empty:
            continue
        observations.append({"symbol":symbol,"date_ny":day,
                             "rth_open":float(rth.iloc[0].open),
                             "rth_close":float(rth.iloc[-1].close)})
    prices=pd.DataFrame(observations)
    if prices.empty:
        raise ValueError("NO_RTH_PRICE_DATA")
    daily=vf.merge(prices,on=["symbol","date_ny"],how="left",validate="one_to_one")
    daily=daily.sort_values(["symbol","date_ny"]).reset_index(drop=True)
    if not daily.loc[daily.complete_rth,["rth_open","rth_close"]].notna().all().all():
        raise ValueError("COMPLETE_RTH_MISSING_OHLC")
    if (daily.loc[daily.complete_rth,["rth_open","rth_close"]]<=0).any().any():
        raise ValueError("NONPOSITIVE_OHLC")
    out=[]
    for symbol,group in daily.groupby("symbol",sort=True):
        d=group.copy()
        c=d.rth_close
        d["price_r5"]=c.pct_change(5,fill_method=None)
        d["price_r20"]=c.pct_change(20,fill_method=None)
        d["price_logvol20"]=np.log(c/c.shift(1)).rolling(20,min_periods=20).std()
        d["next_session_date"]=d.date_ny.shift(-1)
        d["next_session_rth_return"]=(d.rth_close.shift(-1)/d.rth_open.shift(-1)-1)
        # Require the outcome's exchange session fully observed and price adjustment
        # consistent. Never forward-fill incomplete RTH days.
        d.loc[~d.complete_rth.shift(-1,fill_value=False),
              ["next_session_date","next_session_rth_return"]]=pd.NA
        out.append(d)
    result=pd.concat(out,ignore_index=True)
    return result,qa


def matched_cohorts(d:pd.DataFrame,year:int,min_train:int=100,min_test:int=70):
    begin,end=pd.Timestamp(f"{year}-01-01"),pd.Timestamp(f"{year}-12-31")
    valid=(d[PRICE+VOLUME].replace([np.inf,-np.inf],np.nan).notna().all(axis=1)
           &d.next_session_rth_return.notna()&d.complete_rth)
    train=d.loc[valid & d.next_session_date.lt(begin)].sort_values("date_ny").copy()
    test=d.loc[valid & d.date_ny.between(begin,end,inclusive="both")
               &d.next_session_date.le(end)].sort_values("date_ny").copy()
    if len(train)<min_train or len(test)<min_test:
        raise ValueError(f"INSUFFICIENT_PIT_COHORT_{year}:train={len(train)}:test={len(test)}")
    if train.next_session_date.max()>=begin:
        raise AssertionError("TRAIN_LABEL_OVERLAP")
    if set(train.date_ny)&set(test.date_ny):
        raise AssertionError("TRAIN_TEST_SIGNAL_OVERLAP")
    return train,test


def model_quality(train,test,year):
    results={}
    train_ret=train.next_session_rth_return.astype(float).to_numpy()
    test_ret=test.next_session_rth_return.astype(float).to_numpy()
    # Magnitude threshold is fitted strictly on previous training labels
    # (top 25% absolute intraday moves), never chosen on test results.
    move_cutoff=float(np.quantile(np.abs(train_ret),0.75))
    for target in SCREEN_LABELS:
        if target=="direction_up":
            ytr=(train_ret>0).astype(int)
            yte=(test_ret>0).astype(int)
        else:
            ytr=(np.abs(train_ret)>=move_cutoff).astype(int)
            yte=(np.abs(test_ret)>=move_cutoff).astype(int)
        if len(np.unique(ytr))!=2:
            raise ValueError(f"TRAIN_ONE_CLASS_{target}_{year}")
        scores={}
        for name,cols in ARMS.items():
            model=make_pipeline(StandardScaler(),
                                LogisticRegression(C=1.,class_weight="balanced",
                                                   max_iter=1000,random_state=42))
            model.fit(train[cols],ytr)
            probs=model.predict_proba(test[cols])[:,1]
            scores[name]={
                "n_features":len(cols),
                "brier":round(float(brier_score_loss(yte,probs)),7),
                "logloss":round(float(log_loss(yte,probs,labels=[0,1])),7),
                "auc":round(float(roc_auc_score(yte,probs)),7) if len(np.unique(yte))==2 else None,
                "predicted_positive_days":int((probs>=.5).sum()),
                "mean_prob":round(float(np.mean(probs)),7)
            }
        a,b=scores["P_price_3"],scores["V_price_volume_5"]
        results[target]={
            "train_magnitude_cutoff_abs_fraction":round(move_cutoff,7) if target=="next_session_large_move" else None,
            "test_positive_fraction":round(float(np.mean(yte)),7),
            "arms":scores,
            "adding_volume_delta":{
                "brier":round(b["brier"]-a["brier"],7),
                "logloss":round(b["logloss"]-a["logloss"],7),
                "auc":round(b["auc"]-a["auc"],7) if a["auc"] is not None and b["auc"] is not None else None
            },
            "better_when":"Brier/logloss delta negative and AUC delta positive",
            "same_train_test_dates":True
        }
    return {
        "year":year,
        "n_train":len(train),"n_test":len(test),
        "train_exit_max":str(train.next_session_date.max().date()),
        "test_start":str(test.date_ny.min().date()),
        "test_end":str(test.date_ny.max().date()),
        "prediction_target":"NEXT_SESSION_OPEN_TO_CLOSE",
        "models":results
    }


def run_screen(bars):
    daily,qa=build_daily_rows(bars)
    by_symbol={}
    for symbol,d in daily.groupby("symbol",sort=True):
        by_year={}
        for year in YEARS:
            train,test=matched_cohorts(d,year)
            by_year[str(year)]=model_quality(train,test,year)
        by_symbol[symbol]={"yearly":by_year,
                           "train_test_cohort_locked_within_each_year":True,
                           "not_a_live_trading_signal":True}
    return {
        "schema":"kalman-us-multi-five-price-vs-volume-screen-v1",
        "status":"EXPLORATORY_NO_LIVE_GO",
        "source":"ALPACA_SIP_ADJUSTMENT_ALL_15MIN",
        "signal_availability":"RTH_SESSION_CLOSE",
        "earliest_action":"NEXT_SESSION_OPEN",
        "models":ARMS,
        "training":"2024 for 2025; 2024+2025 for 2026 YTD; label exit purged",
        "outcome":"NEXT_SESSION_OPEN_TO_CLOSE, NOT A LIVE RETURN",
        "labels":SCREEN_LABELS,
        "volume_quality":qa,
        "by_symbol":by_symbol,
        "caveats":[
            "AUC/Brier/logloss compare identical test dates within ticker and year; not a profit backtest.",
            "2025 full year vs 2026 partial through October are unequal calendar windows.",
            "These years have been consulted in research: not untouched model-selection validation.",
            "Next-day intraday move is a proxy; transaction costs, limit orders, slippage and overnight gap are not tested.",
            "Future labels are generated from next session prices but never included as model inputs.",
            "The large-move target threshold is the 75th percentile of training-period next-session abs returns, fitted only on past labels.",
            "SIP vendor corporate-action adjustment requires split-related audit before live promotion.",
        ],
        "hold_live":True
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-bars",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    report=run_screen(pd.read_parquet(a.input_bars))
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("MULTISYMBOL_PRICE_VOLUME_SCREEN "+json.dumps({
        "status":report["status"],
        "results":{s:{year:{target:result["adding_volume_delta"]
                 for target,result in dat["models"].items()}
                 for year,dat in rec["yearly"].items()}
                 for s,rec in report["by_symbol"].items()},
        "hold_live":True
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
