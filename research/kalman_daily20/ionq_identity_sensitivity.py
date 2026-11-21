#!/usr/bin/env python3
"""Read-only IONQ predecessor/SPAC sensitivity on immutable Daily20 Actions data.

Two price histories:
 A) provider mapped history from 2021-01-04 (possibly DMYI predecessor)
 B) STRICT IONQ ticker history from 2021-10-01 with TA-Lib recomputed anew
using the same production indicator implementation. No existing market files
are edited; sealed forward journals are NEVER imported or rewritten.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kalman-toss-gateway"))
from engine.features_v2_002.talib_features import build_talib_features

from daily20 import load_bars, load_spec, market_file, feature_file, write_json
from train import COLUMNS, context_frame, feature_frame, model_year, nonoverlap, eligible_row
from regime_challenger import (ML_THRESHOLD, bear_gate, fit_bear_year, rule_gate)
from provenance_audit import fingerprint_feature_row, training_digest, model_digest

CUTOFF = pd.Timestamp("2021-10-01")
ASOF = "2026-11-20"
RUNS = ("44853890794", "44871574162")
ARCHIVES_SHA256 = {
    "44853890794": "3f6166ce09e33f903427ed9fc9a4d5f04c486b10f290ca8f06e055063b7b9ba9",
    "44871574162": "a79197124aba572b1eaeaee2278324de0e14d32ae504fe705aa35f3cc076deb8",
}
RESEARCH_ONLY = True


def sha(blob):
    return sha256(blob).hexdigest()


def cutoff_frame(frame, cutoff=CUTOFF):
    """Do not reuse technical indicators or labels computed on predecessor rows."""
    dates = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    restricted = frame.loc[dates >= cutoff.tz_localize("UTC")].copy()
    if restricted.empty or len(restricted) >= len(frame):
        raise RuntimeError("IONQ_CUTOFF_NO_PREDECESSOR_ROWS")
    if pd.to_datetime(restricted["timestamp"], utc=True).min().date().isoformat() != str(cutoff.date()):
        raise RuntimeError("IONQ_EXPECTED_FIRST_LISTED_DATE_NOT_FOUND")
    return restricted.reset_index(drop=True)


def restore_archive(archive, target):
    with ZipFile(archive) as z:
        names = z.namelist()
        if len(set(names)) != len(names) or any(
            n.startswith("/") or ".." in Path(n).parts or "\\" in n for n in names
        ):
            raise RuntimeError("IONQ_UNSAFE_ACTIONS_SOURCE_ZIP")
        if len(names) != 52:
            raise RuntimeError("IONQ_SOURCE_ARCHIVE_INCOMPLETE")
        if z.testzip() is not None:
            raise RuntimeError("IONQ_ACTIONS_ZIP_CRC_FAILED")
        for name in names:
            path = Path(target) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(z.read(name))


def fold_evidence(frame, year, model_type):
    if model_type == "BULL_LOGISTIC":
        fitted, test, fold = model_year(frame, year)
        train_hash, rows = training_digest(frame, year, bear=False)
    elif model_type == "BEAR_LOGISTIC":
        fitted, test, fold = fit_bear_year(frame, year)
        train_hash, rows = training_digest(frame, year, bear=True)
    else:
        raise ValueError(model_type)
    return {
        "year": year, "model_type": model_type,
        "status": fold["status"], "train_rows": rows,
        "test_rows": int(len(test)) if test is not None else 0,
        "train_sha256": train_hash, "model_sha256": model_digest(fitted),
    }


def trades_for(frame, years, family, *, threshold=0.6):
    parts = []
    for year in years:
        if family.startswith("BULL"):
            fitted, test, _ = model_year(frame, year)
        else:
            fitted, test, _ = fit_bear_year(frame, year)
        if test is None:
            continue
        if family == "BULL_LOGISTIC":
            chosen = ((test["spy_above200_lag"] >= .5)
                      & (test["vix_lag"] <= 35)
                      & test.get("prob", pd.Series(index=test.index, dtype=float)).ge(threshold))
            if fitted is None:
                continue
        elif family == "BULL_RULE":
            chosen = ((test["spy_above200_lag"] >= .5)
                      & (test["vix_lag"] <= 35)
                      & test["sma50_gap"].gt(0)
                      & test["macd_hist"].gt(0)
                      & test["rsi14"].between(45, 70))
        elif family == "BEAR_LOGISTIC":
            if fitted is None:
                continue
            chosen = bear_gate(test) & test["prob"].ge(ML_THRESHOLD)
        elif family == "BEAR_RULE":
            chosen = rule_gate(test)
        else:
            raise ValueError(family)
        chosen &= test["net_return"].notna()
        parts.append(test[chosen])
    if not parts:
        return {"trades":0, "mean_net_return_pct":None, "win_rate":None}
    selected = nonoverlap(pd.concat(parts), "LOGISTIC" if family.endswith("LOGISTIC") else "TREND_RULE")
    vals = np.array([r["net_return"] for r in selected],dtype=float)
    return {"trades":len(selected),
            "mean_net_return_pct":float(vals.mean()*100) if len(vals) else None,
            "win_rate":float((vals>0).mean()) if len(vals) else None}


def summarize(frame, spec, mode):
    years = (2024,2025,2026)
    out = {"mode":mode, "rows":len(frame),
           "first":str(frame.index.min().date()),"last":str(frame.index.max().date()),
           "asof_feature_sha256":fingerprint_feature_row(frame,ASOF),
           "feature_columns":len(COLUMNS),
           "annual_folds":[fold_evidence(frame,y,t) for y in years
                           for t in ("BULL_LOGISTIC","BEAR_LOGISTIC")],
           "historical_trades":{f:trades_for(frame,years,f)
                for f in ("BULL_LOGISTIC","BULL_RULE","BEAR_LOGISTIC","BEAR_RULE")}}
    last = frame.loc[[pd.Timestamp(ASOF)]]
    for typ in ("BULL_LOGISTIC","BEAR_LOGISTIC"):
        if typ.startswith("BULL"):
            fitted,_,_ = model_year(frame,2026)
            candidate_gate = eligible_row(last.iloc[0])
            cutoff = float(spec["probability_threshold"])
        else:
            fitted,_,_=fit_bear_year(frame,2026)
            candidate_gate = bool(bear_gate(last).iloc[0])
            cutoff = ML_THRESHOLD
        prob = float(fitted.predict_proba(last[COLUMNS])[:,1][0]) if fitted is not None else None
        out[typ+"_current"]={"prob":prob,
            "candidate":bool(candidate_gate and prob is not None and prob>=cutoff)}
    out["BEAR_RULE_current"]={"candidate":bool(rule_gate(frame).iloc[-1])}
    return out


def run_one(spec, artifact, run_id, out):
    artifact=Path(artifact)
    if sha(artifact.read_bytes())!=ARCHIVES_SHA256[run_id]:
        raise RuntimeError("IONQ_SOURCE_ARTIFACT_SHA256_WRONG:" + run_id)
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        original=root/"original"
        restore_archive(artifact,original)
        market=original/"market"
        features=original/"features"
        raw=pd.read_parquet(market_file(market,"IONQ"))
        context=context_frame(market)
        baseline=feature_frame("IONQ",market,features,context,
                               float(spec["round_trip_cost_bps"]))
        original_cols=len(raw)
        cut=cutoff_frame(raw)
        gated_m=root/"gated_market"
        gated_f=root/"gated_features"
        p=market_file(gated_m,"IONQ")
        p.parent.mkdir(parents=True,exist_ok=True)
        cut.to_parquet(p,index=False)
        new_ta=build_talib_features(cut)
        q=feature_file(gated_f,"IONQ")
        q.parent.mkdir(parents=True,exist_ok=True)
        new_ta.to_parquet(q,index=False)
        restricted=feature_frame("IONQ",gated_m,gated_f,context,
                                 float(spec["round_trip_cost_bps"]))
        assert str(restricted.index.min().date())=="2021-10-01"
        assert baseline.index[-1] == restricted.index[-1] == pd.Timestamp(ASOF)
        # Same source post-listing OHLCV rows: no price rewrites or trade changes.
        existing=load_bars(market_file(market,"IONQ")).loc[CUTOFF:]
        clean=load_bars(p)
        assert existing[["open","high","low","close","volume"]].equals(
            clean[["open","high","low","close","volume"]])
        exam_dates=("2021-01-04","2021-03-05","2021-09-30","2021-10-01","2021-10-04")
        original_ohlcv=load_bars(market_file(market,"IONQ"))
        sample={d:({"close":float(original_ohlcv.loc[pd.Timestamp(d),"close"]),
                    "volume":float(original_ohlcv.loc[pd.Timestamp(d),"volume"])}
                  if pd.Timestamp(d) in original_ohlcv.index else None)
                for d in exam_dates}
        base=summarize(baseline,spec,"PROVIDER_FULL_WITH_PRELISTING")
        gated=summarize(restricted,spec,"IONQ_LISTED_ONLY_RECOMPUTED_TA")
        results={"run_id":run_id,"status":"RESEARCH_ONLY",
                 "source_archive_sha256":ARCHIVES_SHA256[run_id],
                 "cutoff_session":"2021-10-01",
                 "prelisting_raw_bars_excluded":int(original_cols-len(cut)),
                 "raw_first":str(pd.to_datetime(raw["timestamp"],utc=True).min().date()),
                 "raw_last":str(pd.to_datetime(raw["timestamp"],utc=True).max().date()),
                 "provider_original_ohlcv_samples":sample,
                 "baseline":base,"gated":gated,
                 "deltas":{},"not_saved_to_drive":True,
                 "sealed_forward_journal_modified":False,
                 "strategy_promoted":False}
        for family in ("BULL_LOGISTIC","BEAR_LOGISTIC"):
            old=base[family+"_current"];new=gated[family+"_current"]
            results["deltas"][family+"_prob_pp"]=(
                100*(new["prob"]-old["prob"])
                if old["prob"] is not None and new["prob"] is not None else None)
            results["deltas"][family+"_candidate_flip"]=old["candidate"]!=new["candidate"]
        results["deltas"]["bear_rule_candidate_flip"]=(
            base["BEAR_RULE_current"]["candidate"]!=gated["BEAR_RULE_current"]["candidate"])
        results["deltas"]["current_21_feature_changed"]=(
            base["asof_feature_sha256"]!=gated["asof_feature_sha256"])
        out.mkdir(parents=True,exist_ok=True)
        write_json(out/(run_id+"_ionq_sensitivity.json"),results)
        print("IONQ_IDENTITY_SENSITIVITY",json.dumps({"run":run_id,
            "removed_prelisting":results["prelisting_raw_bars_excluded"],
            "bull_prob_delta_pp":results["deltas"]["BULL_LOGISTIC_prob_pp"],
            "bear_prob_delta_pp":results["deltas"]["BEAR_LOGISTIC_prob_pp"],
            "feature_changed":results["deltas"]["current_21_feature_changed"]}))
        return results


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--left",required=True)
    ap.add_argument("--right",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--config",default="research/kalman_daily20/universe.json")
    a=ap.parse_args()
    spec=load_spec(a.config)
    folder=Path(a.out)
    left=run_one(spec,a.left,RUNS[0],folder)
    right=run_one(spec,a.right,RUNS[1],folder)
    dashboard={
        "version":"ionq-prelisting-sensitivity-v1",
        "research_only":True,"no_live_changes":True,
        "source_versions":list(RUNS),
        "ticker_inception":"2021-10-01",
        "predecessor_identity_status":"HYPOTHESIS_DMYI_NOT_INDEPENDENTLY_PRICE_MATCHED",
        "results":{
            r["run_id"]:{
                "excluded_prelisting_bars":r["prelisting_raw_bars_excluded"],
                "current_asof_features_changed":r["deltas"]["current_21_feature_changed"],
                "bull_probability_delta_pp":r["deltas"]["BULL_LOGISTIC_prob_pp"],
                "bear_probability_delta_pp":r["deltas"]["BEAR_LOGISTIC_prob_pp"],
                "bear_rule_flip":r["deltas"]["bear_rule_candidate_flip"],
                "historical_trades_original":r["baseline"]["historical_trades"],
                "historical_trades_listed_only":r["gated"]["historical_trades"],
            } for r in (left,right)
        },
        "recommendation":"HOLD any prelisting IONQ labeling before corporate-action identity provenance is independently confirmed.",
    }
    write_json(folder/"ionq_sensitivity_overview.json",dashboard)
    print("IONQ_IDENTITY_SENSITIVITY_OVERVIEW",json.dumps(dashboard))


if __name__=="__main__":
    main()
