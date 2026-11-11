#!/usr/bin/env python3
"""Outcome-blind four-arm price/regime × QLD/QQQ volume study.

This creates a *new* research comparison without modifying the original
5-feature/10-feature classifiers, 40-axis joint policy, or LIVE trades.

All arms use identical common-complete training/test signal dates, unchanged
fixed 3% TP / 3% SL / four-session policy, same labels and cost ledger.
Daily volume features use the completed RTH session at signal close, so the
earliest eligible entry is the next NYSE session. No tuned thresholds.
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

from research.kalman_integrated_regime import run as base
from research.kalman_integrated_regime.volume_features import volume_features

VOLUME = ["qqq_rvol20", "qld_rvol20", "qqq_volume_z20", "qld_volume_z20"]
ARMS = {
    "A_price_5": list(base.PRICE),
    "B_price_volume_9": list(base.PRICE) + VOLUME,
    "C_integrated_10": list(base.PRICE) + list(base.EXTRA),
    "D_integrated_volume_14": list(base.PRICE) + list(base.EXTRA) + VOLUME,
}
PAIRS = (("A_price_5", "B_price_volume_9"),
         ("C_integrated_10", "D_integrated_volume_14"))


def common_eligible(features: pd.DataFrame) -> pd.Series:
    wanted = list(dict.fromkeys(col for cols in ARMS.values() for col in cols))
    missing = [k for k in wanted if k not in features.columns]
    if missing:
        raise ValueError("MISSING_ABLATION_FEATURES:"+",".join(missing))
    return features[wanted].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)


def paired_cohorts(features, events, year, min_train=80):
    """Purge by completed EXIT for train; lock dates across all four models."""
    begin, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
    valid = common_eligible(features)
    train = events.loc[events.exit_date.lt(begin)].sort_values("date")
    test = events.loc[
        events.date.between(begin, end, inclusive="both") &
        events.exit_date.le(end)
    ].sort_values("date")
    train = train.loc[train.date.map(valid).fillna(False)].copy()
    test = test.loc[test.date.map(valid).fillna(False)].copy()
    if len(train) < min_train or train.positive.nunique() < 2:
        raise ValueError(f"TRAIN_UNUSABLE_{year}:{len(train)}")
    if len(test) < 30 or test.positive.nunique() < 2:
        raise ValueError(f"TEST_UNUSABLE_{year}:{len(test)}")
    if train.exit_date.max() >= begin:
        raise AssertionError("TRAIN_LABEL_OVERLAP")
    if set(train.date) & set(test.date):
        raise AssertionError("TRAIN_TEST_SIGNAL_OVERLAP")
    return train, test


def compare_annual(features, events, complete, year):
    """Fit all arms on identical labeled dates, evaluate fixed policy unchanged."""
    train, test = paired_cohorts(features, events, year)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
    sessions = {d:complete[d] for d in sorted(complete)
                if start <= d <= end}
    by_arm = {}
    for arm, columns in ARMS.items():
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=1., class_weight="balanced",
                               max_iter=1000, random_state=42))
        model.fit(features.loc[train.date, columns], train.positive)
        probs = model.predict_proba(features.loc[test.date, columns])[:, 1]
        pred = test.loc[probs >= 0.50].copy()
        selected = base.select_nonoverlap(pred)
        outcome = base.metrics(selected, sessions)
        y = test.positive.to_numpy(dtype=int)
        outcome.update({
            "num_features":len(columns),
            "features":columns,
            "selection_probability":0.5,
            "predicted_signal_days":int(len(pred)),
            "train_labeled":int(len(train)),
            "test_labeled":int(len(test)),
            "train_last_label_exit":str(train.exit_date.max().date()),
            "test_first_signal":str(test.date.min().date()),
            "test_last_signal":str(test.date.max().date()),
            "brier_score":round(float(brier_score_loss(y, probs)),7),
            "log_loss":round(float(log_loss(y, probs,labels=[0,1])),7),
            "roc_auc":round(float(roc_auc_score(y, probs)),7),
            "mean_model_probability":round(float(np.mean(probs)),7),
            "observed_positive_label_rate":round(float(np.mean(y)),7),
        })
        by_arm[arm] = outcome
    contrasts = {}
    for without, with_volume in PAIRS:
        a, b = by_arm[without], by_arm[with_volume]
        contrasts[f"{with_volume}_minus_{without}"] = {
            "return_delta_percentage_points":
                round(b["return_pct"]-a["return_pct"],5),
            "mdd_delta_percentage_points":
                round(b["mdd_daily_mark_pct"]-a["mdd_daily_mark_pct"],5),
            "completed_trades_delta": b["trades"]-a["trades"],
            "brier_delta":round(b["brier_score"]-a["brier_score"],7),
            "logloss_delta":round(b["log_loss"]-a["log_loss"],7),
            "auc_delta":round(b["roc_auc"]-a["roc_auc"],7),
        }
    return {"year":year,"arms":by_arm,"contrasts":contrasts,
            "identical_training_cohort":True,
            "identical_test_signal_cohort":True,
            "fixed_execution_settings":
                {"tp":base.TP,"sl":base.SL,"max_hold_sessions":base.HOLD,
                 "fee_each_side":base.FEE,
                 "entry":"NEXT_SESSION_OPEN",
                 "barrier_same_bar":"STOP_FIRST"}}


def research_report(daily_path, intraday_path, market_zip_path):
    prices=base.read_prices(daily_path)
    macro=base.read_market_zip(market_zip_path)
    candles=pd.read_parquet(intraday_path)
    volume, volume_qa=volume_features(candles,history=20)
    current=base.build_features(prices,macro)
    if volume.index.has_duplicates or current.index.has_duplicates:
        raise AssertionError("DUPLICATE_FEATURE_DAY")
    extra=volume.reindex(current.index)
    for col in VOLUME:
        current[col]=extra[col].astype(float)
    # Price/day labels and 15m barrier paths are original, unmodified.
    x=base.read_15m(intraday_path)
    complete, integrity=base.complete_sessions(x,prices.index)
    events=base.label_events(prices.index,complete)
    if events.empty:
        raise ValueError("NO_FIXED_BARRIER_EVENTS")
    yearly={}
    for year in (2025,2026):
        yearly[str(year)]=compare_annual(current, events, complete, year)
    return {
        "schema":"kalman-qld-qqq-four-arm-volume-increment-v1",
        "status":"EXPLORATORY_POLICY_SELECTION_NOT_FRESH_OOS",
        "model_type":"CLASS_BALANCED_LOGISTIC_REGRESSION",
        "training_policy":"EXPANDING_WALK_FORWARD_WITH_TRADE_EXIT_PURGE",
        "precommitted_arms":ARMS,
        "volume_columns":VOLUME,
        "volume_method":"COMPLETED_RTH_VOLUME_OVER_PRIOR_20_SESSIONS",
        "decision_time":"AFTER_NYSE_CLOSE; EARLIEST_ENTRY_NEXT_SESSION",
        "same_date_cohort_for_all_four_models":True,
        "zero_or_partial_bar_imputation":False,
        "same_original_fixed_barrier_exits":True,
        "live_execution_modified":False,
        "hold_live":True,
        "volume_source_qa":volume_qa,
        "qld_15m_session_qa":{
            "complete":integrity["complete"],
            "missing":integrity["missing"],
            "partial":integrity["partial"],
        },
        "total_fixed_barrier_events":int(len(events)),
        "yearly":yearly,
        "limits":[
            "Historical 2025/2026 already used extensively for selecting research designs, not untouched policy OOS.",
            "Alpaca SIP bars use adjustment=all; corporate-action adjusted volume denominator must match adjusted shares and split events.",
            "Same full-data coverage for 2024 features is required; volume data missing => paired-cohort date removal.",
            "Close/day signal must only be acted on next session; intrabar signal/large-trade effects not measured here.",
            "No independent market-impact or live-slippage audit; original fixed fee and conservative barrier path reused.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--daily",required=True)
    p.add_argument("--intraday",required=True)
    p.add_argument("--market-zip",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    report=research_report(args.daily,args.intraday,args.market_zip)
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    (output/"volume_four_arm_results.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("VOLUME_ABLATION_REPORT "+json.dumps({
        "status":report["status"],
        "source_qa":report["volume_source_qa"],
        "years":{year:{
            "arms":{k:{x:v.get(x) for x in ("return_pct","mdd_daily_mark_pct",
                                           "trades","brier_score","log_loss","roc_auc")}
                    for k,v in record["arms"].items()},
            "contrasts":record["contrasts"],
            "paired_test_size":next(iter(record["arms"].values()))["test_labeled"]
        }for year,record in report["yearly"].items()},
        "live_hold":True},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
