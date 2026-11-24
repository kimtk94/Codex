#!/usr/bin/env python3
"""Research-only volume regime drift and paired signal-change attribution.

Uses the exact 5/9/10/14 arm logic and fixed-barrier labeled trade cohort from
volume_four_arm.py. Produces aggregate-only output (NO raw SIP or individual fills).

This is DESCRIPTIVE evidence; performance in 2025/2026 has been repeatedly
consulted and cannot establish fresh OOS alpha or causation.
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

from research.kalman_integrated_regime import run as base
from research.kalman_integrated_regime.volume_features import volume_features
from research.kalman_integrated_regime.volume_four_arm import (
    ARMS, VOLUME, PAIRS, paired_cohorts,
)


def numeric_summary(values):
    x = pd.to_numeric(pd.Series(values), errors="coerce").replace(
        [np.inf, -np.inf], np.nan).dropna()
    return {
        "n": int(len(x)),
        "mean": round(float(x.mean()), 6) if len(x) else None,
        "median": round(float(x.median()), 6) if len(x) else None,
        "p10": round(float(x.quantile(.1)), 6) if len(x) else None,
        "p90": round(float(x.quantile(.9)), 6) if len(x) else None,
        "p99": round(float(x.quantile(.99)), 6) if len(x) else None,
    }


def collect_drift(features, events, year):
    """Identical full A/B/C/D test cohort; no future-volume leakage."""
    train, test = paired_cohorts(features, events, year)
    by_year = {}
    signal_dates = pd.DatetimeIndex(test.date)
    signal_features = features.loc[signal_dates]
    labels = test.set_index("date")["positive"].astype(int)
    for f in ("qqq_rvol20", "qld_rvol20", "qqq_volume_z20", "qld_volume_z20",
              "qqq_r5", "qld_r5", "qqq_vol20", "vix_lag1"):
        by_year[f] = numeric_summary(signal_features[f])
    for sym in ("qqq", "qld"):
        s = signal_features[f"{sym}_rvol20"]
        by_year[f"{sym}_rvol20_over2_fraction"] = round(float((s>=2).mean()), 6)
    by_year["positive_label_fraction"] = round(float(labels.mean()), 6)
    by_year["down_qqq_r5_fraction"] = round(float((signal_features.qqq_r5<0).mean()), 6)
    by_year["num_train"] = int(len(train))
    by_year["num_test"] = int(len(test))

    probs = {}
    for arm, cols in ARMS.items():
        model = make_pipeline(StandardScaler(),
                              LogisticRegression(C=1., class_weight="balanced",
                                                 max_iter=1000, random_state=42))
        model.fit(features.loc[train.date,cols], train.positive)
        prediction = model.predict_proba(features.loc[signal_dates,cols])[:,1]
        probs[arm] = pd.Series(prediction,index=signal_dates)
    contrasts={}
    for old,new in PAIRS:
        oldp, newp = probs[old], probs[new]
        old_signal, new_signal = oldp >= .5, newp >= .5
        both = old_signal & new_signal
        added = ~old_signal & new_signal
        removed = old_signal & ~new_signal
        neither = ~old_signal & ~new_signal
        # These are candidate *signal-day* labels; nonoverlap means actual
        # executed trades differ, reported separately by volume_four_arm.
        def class_summary(mask):
            subset=signal_dates[mask.to_numpy()]
            idx=features.loc[subset]
            y=labels.loc[subset]
            return {
                "candidate_signal_days":int(mask.sum()),
                "positive_barrier_label_fraction":
                    round(float(y.mean()),6) if len(y) else None,
                "qqq_rvol20":numeric_summary(idx.qqq_rvol20),
                "qld_rvol20":numeric_summary(idx.qld_rvol20),
                "qqq_r5":numeric_summary(idx.qqq_r5),
                "qqq_vol20":numeric_summary(idx.qqq_vol20),
            }
        contrasts[new+"_minus_"+old]={
            "same_cohort_days":int(len(test)),
            "both_signal":class_summary(both),
            "added_by_volume":class_summary(added),
            "removed_by_volume":class_summary(removed),
            "neither_signal":class_summary(neither),
            "predicted_probability_shift_new_minus_old":
                numeric_summary(newp-oldp),
            "new_probability_mean":round(float(newp.mean()),7),
            "old_probability_mean":round(float(oldp.mean()),7),
            "threshold":.5,
            "not_a_causal_trade_level_attribution":True,
            "counts_include_overlapping_trade_candidates":True,
        }
        if sum(contrasts[new+"_minus_"+old][part]["candidate_signal_days"]
               for part in ("both_signal","added_by_volume",
                            "removed_by_volume","neither_signal")) != len(test):
            raise AssertionError("SIGNAL_COHORT_PARTITION_FAILED")
    return {"year":year,"features":by_year,"pair_signal_contrasts":contrasts,
            "signal_day_cohort_fixed_across_arms":True}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--daily",required=True)
    ap.add_argument("--intraday",required=True)
    ap.add_argument("--market-zip",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    daily=base.read_prices(a.daily)
    features=base.build_features(daily,base.read_market_zip(a.market_zip))
    v,vqa=volume_features(pd.read_parquet(a.intraday),history=20)
    for col in VOLUME:
        features[col]=v[col].reindex(features.index).astype(float)
    x=base.read_15m(a.intraday)
    complete,integrity=base.complete_sessions(x,daily.index)
    events=base.label_events(daily.index,complete)
    yearly={str(y):collect_drift(features,events,y) for y in (2025,2026)}
    report={"schema":"qld-volume-feature-and-signal-drift-2025-2026-v1",
            "status":"DESCRIPTIVE_RESEARCH_NOT_CAUSAL",
            "source_coverage":vqa,"signal_years":yearly,
            "notes":[
                "A signal candidate is NOT a nonoverlapping executed trade.",
                "Positive barrier labels use original fixed TP3/SL3/4d horizon.",
                "Average RVOL does not imply causal volume-driven return.",
                "Scikit-learn model prediction scores can change because their fitted coefficients, baseline label rates and market regimes all vary between years.",
                "For both year comparisons, 2025 and 2026 were previously evaluated, so research questions are now adaptive and not untouched OOS.",
                "SIP bar volume does not contain buy-side and sell-side aggressor classification.",
            ],"hold_live":True}
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"volume_regime_drift.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("VOLUME_REGIME_DRIFT "+json.dumps({
        "status":report["status"],
        "yearly":yearly,"hold_live":True
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
