#!/usr/bin/env python3
"""COIN frozen-model prospective shadow signal: never broker, never LIVE.

Only a completed 2026-11-02+ NYSE decision day can be sealed in a research
audit branch. Public output exposes a commitment, never direction/probability,
SIP rows, private model coefficients or exact trading levels.

Training set is permanently cut off before 2026-01-01, exactly as the original
V_unweighted 2026 experiment. All 2026 viewed data are validation only.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

FREEZE = date(2026, 11, 1)
FIRST_NEW_DECISION = date(2026, 11, 2)
TRAIN_BOUNDARY = date(2026, 1, 1)
ORIGINAL_SHA = "cccbb80059ab626da0cbd76cd825f879870f6727"
THRESHOLD = .5
FEATURES = ("price_r5", "price_r20", "price_logvol20", "rvol20", "volume_z20")
NY = ZoneInfo("America/New_York")
UTC = timezone.utc


class ResearchHold(RuntimeError):
    pass


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def sha(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


def check_decision_clock(asof, now, calendar, *, prospective=True):
    """Fail closed unless the current NYSE session has closed and next has not opened."""
    if now.tzinfo is None:
        raise ResearchHold("NAIVE_CLOCK")
    if not calendar.is_session(str(asof)):
        raise ResearchHold("ASOF_NOT_NYSE_SESSION")
    if not prospective:
        if asof >= FIRST_NEW_DECISION:
            raise ResearchHold("RETROSPECTIVE_SMOKE_MUST_BE_PRE_FREEZE")
        return calendar.next_session(str(asof)).date()
    if asof < FIRST_NEW_DECISION:
        raise ResearchHold("PRE_FREEZE_NOT_OOS")
    if now.astimezone(NY).date() != asof:
        raise ResearchHold("NO_CURRENT_NYSE_SESSION_TO_SEAL")
    close = calendar.session_close(str(asof)).to_pydatetime()
    if now < close + timedelta(minutes=20):
        raise ResearchHold("SESSION_NOT_COMPLETELY_CLOSED")
    next_day = calendar.next_session(str(asof))
    if now >= calendar.session_open(next_day).to_pydatetime():
        raise ResearchHold("SEAL_ATTEMPT_AFTER_NEXT_OPEN")
    return next_day.date()


def frozen_signal(bars, asof, *, snapshot=None):
    """Original source-family 2026 model exactly; no fitted data after 2025."""
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
        build_daily_rows, PRICE, VOLUME)
    assert tuple(PRICE+VOLUME) == FEATURES, "ORIGINAL_FEATURE_DRIFT"
    if set(bars.market.astype(str)) != {"COIN"}:
        raise ResearchHold("WRONG_SINGLE_SYMBOL")
    stamps = pd.to_datetime(bars.candle_time_utc, utc=True)
    if stamps.isna().any() or (stamps.dt.tz_convert(NY).dt.date > asof).any():
        raise ResearchHold("FUTURE_BARS_IN_DECISION_SOURCE")
    if bars.duplicated(["market","candle_time_utc"]).any():
        raise ResearchHold("DUPLICATE_SOURCE_BARS")
    frame, quality = build_daily_rows(bars)
    frame = frame.loc[frame.symbol.eq("COIN")].sort_values("date_ny")
    selected = frame.loc[frame.date_ny.eq(pd.Timestamp(asof))]
    if len(selected)!=1 or not bool(selected.iloc[0].complete_rth):
        raise ResearchHold("INCOMPLETE_ASOF_RTH")
    if not bool(frame.iloc[-1].date_ny==pd.Timestamp(asof)):
        raise ResearchHold("LATEST_RTH_DATE_NOT_ASOF")
    valid = (frame[list(FEATURES)].replace([np.inf,-np.inf],np.nan).notna().all(axis=1)
             &frame.next_session_rth_return.notna()&frame.complete_rth)
    train = frame.loc[valid & frame.next_session_date.lt(pd.Timestamp(TRAIN_BOUNDARY))
                      &frame.date_ny.lt(pd.Timestamp(TRAIN_BOUNDARY))].copy()
    if len(train) < 100:
        raise ResearchHold("FROZEN_TRAIN_TOO_SMALL")
    if train.next_session_date.max() >= pd.Timestamp(TRAIN_BOUNDARY):
        raise ResearchHold("TRAIN_OUTCOME_LEAKAGE")
    y=(train.next_session_rth_return.to_numpy(dtype=float)>0).astype(int)
    if len(set(y))!=2:
        raise ResearchHold("ONE_TRAIN_CLASS")
    row=selected.iloc[0]
    values=row[list(FEATURES)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ResearchHold("LATEST_FEATURE_NOT_FULLY_KNOWN")
    model=make_pipeline(StandardScaler(),
        LogisticRegression(class_weight=None,C=1.,random_state=42,max_iter=1000))
    model.fit(train[list(FEATURES)],y)
    score=float(model.predict_proba(pd.DataFrame(
        [dict(zip(FEATURES,values))]))[0,1])
    if not 0<=score<=1:
        raise ResearchHold("INVALID_MODEL_PROBABILITY")
    reg=model.named_steps["logisticregression"]
    scaler=model.named_steps["standardscaler"]
    fitted={
        "classifier_coefficients_hex":[float(x).hex() for x in reg.coef_[0]],
        "intercept_hex":float(reg.intercept_[0]).hex(),
        "scaler_means_hex":[float(x).hex() for x in scaler.mean_],
        "scaler_scales_hex":[float(x).hex() for x in scaler.scale_],
        "fitted_train_rows":len(train),
        "train_last_label_date":str(train.next_session_date.max().date()),
        "features":list(FEATURES),
        "fixed_training_boundary":"2026-01-01",
        "original_sha":ORIGINAL_SHA,
    }
    return {"score":score,"candidate":score>=THRESHOLD,
            "model_digest":sha(fitted),
            "train_last_label_date":fitted["train_last_label_date"],
            "train_count":len(train),
            "available_features_hex":{k:float(v).hex() for k,v in zip(FEATURES,values)},
            "input_bar_digest":hashlib.sha256(
                pd.util.hash_pandas_object(bars.sort_values("candle_time_utc"),
                                          index=False).values.tobytes()).hexdigest(),
            "quality":quality}


def make_commitment(asof,entry_date,signal):
    """Opaque public hash of complete *private* decision, not a directional flag."""
    return sha({"decision_date":asof.isoformat(),"next_entry":entry_date.isoformat(),
                "source_sha":ORIGINAL_SHA,"model_digest":signal["model_digest"],
                "input_bar_digest":signal["input_bar_digest"],
                "signal_probability":float(signal["score"]).hex(),
                "candidate":signal["candidate"],
                "features":signal["available_features_hex"]})


def produce(bars,asof,now,*,prospective,calendar,original_snapshot_sha):
    if original_snapshot_sha!=ORIGINAL_SHA:
        raise ResearchHold("ORIGINAL_SOURCE_SHA_MISMATCH")
    entry=check_decision_clock(asof,now,calendar,prospective=prospective)
    prediction=frozen_signal(bars,asof)
    digest=make_commitment(asof,entry,prediction)
    is_oos=prospective and asof>=FIRST_NEW_DECISION
    status=("SEALED_PRE_ENTRY_OOS_SHADOW" if is_oos
            else "RETROSPECTIVE_SMOKE_NO_OOS_CREDIT")
    public={"schema":"coin-prospective-research-snapshot-v1",
            "status":status,"asof_nyse_session":asof.isoformat(),
            "earliest_entry_session":entry.isoformat(),
            "model_family":"PINNED_2026_V_UNWEIGHTED",
            "source_commit":ORIGINAL_SHA,
            "train_labels_end_before":"2026-01-01",
            "freeze_date":"2026-11-01",
            "signal_commitment_sha256":digest,
            "model_commitment_sha256":prediction["model_digest"],
            "decision_signaled_after_rth_close":True,
            "signal_and_price_not_public":True,
            "not_an_order_not_a_fill":True,
            "no_unseen_oos_claim_for_smoke":not is_oos,
            "live":"HOLD"}
    secret={"schema":"coin-private-prospective-signal-v1",
            "asof_nyse_session":asof.isoformat(),
            "next_entry_session":entry.isoformat(),
            "source_sha":ORIGINAL_SHA,
            "signal_probability":prediction["score"],
            "candidate":prediction["candidate"],
            "features":prediction["available_features_hex"],
            "model_digest":prediction["model_digest"],
            "bars_digest":prediction["input_bar_digest"],
            "signal_commitment_sha256":digest,
            "available_after_rth_only":True,
            "not_a_broker_order":True}
    return public,secret


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("smoke","prospective"),required=True)
    p.add_argument("--asof",required=True)
    p.add_argument("--bars-parquet",type=Path,required=True)
    p.add_argument("--original-source",type=Path,required=True)
    p.add_argument("--public-out",type=Path,required=True)
    p.add_argument("--private-out",type=Path,required=True)
    p.add_argument("--allow-smoke-only",action="store_true",
                   help="For repository PR test; never write prospective journal")
    args=p.parse_args()
    import exchange_calendars as xcals
    asof=date.fromisoformat(args.asof)
    prospective=args.mode=="prospective"
    if args.allow_smoke_only and prospective:
        raise ResearchHold("PR_SMOKE_MUST_NOT_SEAL_PROSPECTIVE")
    if not args.original_source.exists():
        raise ResearchHold("ORIGINAL_SNAPSHOT_NOT_FOUND")
    import subprocess
    gitsha=subprocess.check_output(
        ["git","-C",str(args.original_source),"rev-parse","HEAD"],
        text=True).strip()
    sys.path.insert(0,str(args.original_source.resolve()))
    import pandas as pd
    bars=pd.read_parquet(args.bars_parquet)
    public,private=produce(bars,asof,datetime.now(UTC),
         prospective=prospective,calendar=xcals.get_calendar("XNYS"),
         original_snapshot_sha=gitsha)
    args.public_out.parent.mkdir(parents=True,exist_ok=True)
    args.public_out.write_text(json.dumps(public,indent=2,sort_keys=True)+"\n")
    args.private_out.parent.mkdir(parents=True,exist_ok=True)
    args.private_out.write_text(json.dumps(private,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":public["status"],"asof":public["asof_nyse_session"],
         "commitment":public["signal_commitment_sha256"],"live":"HOLD"}))


if __name__=="__main__":
    main()
