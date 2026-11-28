"""Standard-Parquet reproduction of frozen OHLC and full-feature risk results.

Fixed cohorts and close-observed decisions followed by next-session open
exits. No intraday stop execution or portfolio reallocations. Read only.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from outcome_profile import (
    ARCHIVES, ASOF, FEATURES, KEY, FAMILIES, load_archive, load_original,
    csv, normalize_keys, join_signal_features, trailing_diagnostics, match_executions,
)
from risk_pilot import annual_split, admissible, logistic, classification

DAYS = (1, 2, 3)
THRESHOLDS = (-.02, -.05)
COSTS = (20, 40)


def path_from_ohlc(bars, event):
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("INVALID_BAR_CALENDAR")
    i = bars.index.get_loc(event.signal_date)
    w = bars.iloc[i+1:i+5][["open", "high", "low", "close"]]
    if len(w)!=4 or w.index[0]!=event.entry_date or w.index[-1]!=event.exit_date:
        raise ValueError("HOLD_WINDOW_MISMATCH")
    if not np.isfinite(w).all().all() or not w.gt(0).all().all():
        raise ValueError("INVALID_OHLC")
    if (w.high.lt(w[["open","low","close"]].max(axis=1)-1e-8).any()
            or w.low.gt(w[["open","high","close"]].min(axis=1)+1e-8).any()):
        raise ValueError("INCONSISTENT_OHLC")
    op = w.open.iloc[0]
    gross = w.close.iloc[-1]/op-1
    if abs(gross-event.gross_return)>2e-6 or abs(gross-.002-event.net_return)>2e-6:
        raise ValueError("ORIGINAL_LABEL_MISMATCH")
    return {
        "mfe": float(max(0,w.high.max()/op-1)),
        "mae": float(min(0,w.low.min()/op-1)),
        **{f"close{j+1}":float(x/op-1) for j,x in enumerate(w.close)},
        **{f"open{j+1}":float(x/op-1) for j,x in enumerate(w.open)},
        "gross_label_abs_error":float(abs(gross-event.gross_return)),
    }


def net(gross,cost,filled):
    half = cost/20000.
    return (1+gross)*(1-half)/(1+half)-1 if filled else gross-cost/10000.


def policy(frame,day,threshold,cost,filled):
    """One fixed checkpoint only. Use next actual open, not trigger close."""
    if day not in DAYS or threshold not in THRESHOLDS or cost not in COSTS:
        raise ValueError("UNREGISTERED_CHECKPOINT")
    original = net(frame.close4,cost,filled)
    if filled and not np.allclose(original,frame.realized_return,atol=2e-6,rtol=0):
        raise ValueError("LEDGER_RETURN_MISMATCH")
    trigger = net(frame[f"close{day}"],cost,filled).le(threshold)
    alternate = original.where(~trigger,net(frame[f"open{day+1}"],cost,filled))
    delta = alternate-original
    return {
        "day":day,"threshold":threshold,"n":len(frame),"trigger_count":int(trigger.sum()),
        "mean_original":float(original.mean()),"mean_alternate":float(alternate.mean()),
        "mean_paired_delta":float(delta.mean()),
        "severe_original":int(original.le(-.05).sum()),"severe_alternate":int(alternate.le(-.05).sum()),
        "winners_to_nonwins":int((original.gt(0)&alternate.le(0)).sum()),
        "nonwins_to_winners":int((original.le(0)&alternate.gt(0)).sum()),
        "year_delta":{str(y):float(delta.loc[g.index].mean()) for y,g in frame.groupby("year")},
        "portfolio_resimulated":False,
    }


def excursion_groups(frame,cost,filled):
    r=net(frame.close4,cost,filled)
    groups={"WIN":r.gt(0),"MILD_LOSS":r.lt(0)&r.gt(-.05),"SEVERE_LOSS":r.le(-.05),
            "BREAKEVEN":r.eq(0)}
    return {k:{"n":int(mask.sum()),"mfe_median":float(frame.loc[mask,"mfe"].median()),
               "mae_median":float(frame.loc[mask,"mae"].median())}
            for k,mask in groups.items() if mask.any()}


def full_risk(data,calendar):
    g=data.loc[data.family.eq("BULL_LOGISTIC")].copy()
    g["severe"]=g.net_return.le(-.05).astype(int)
    predictions,folds=[],[]
    models={"VOL20":["vol20"],"NATR14":["natr14"],"ALL21":list(FEATURES),
            "ALL21_SCORE":[*FEATURES,"probability"]}
    for year in (2025,2026):
        tr,te,cutoff=annual_split(g,calendar,year)
        if not admissible(tr,te):
            raise ValueError("INSUFFICIENT_BULL_TRAINING_EVIDENCE")
        if not np.isfinite(tr[[*FEATURES,"vol20","probability"]]).all().all() or not np.isfinite(
                te[[*FEATURES,"vol20","probability"]]).all().all():
            raise ValueError("INCOMPLETE_FEATURES")
        prior=tr.severe.mean()
        counts=tr.groupby("symbol").severe.agg(["sum","count"])
        rates=(counts["sum"]+10*prior)/(counts["count"]+10)
        te["SYMBOL_PRIOR"]=te.symbol.map(rates).fillna(prior)
        for m,cols in models.items():
            te[m]=logistic(tr[cols],tr.severe).predict_proba(te[cols])[:,1]
        folds.append({"year":year,"train_n":len(tr),"test_n":len(te),
                      "cutoff":str(cutoff.date()),"severe_test":int(te.severe.sum()),
                      "metrics":{m:classification(te.severe,te[m])
                                 for m in ("SYMBOL_PRIOR",*models)}})
        predictions.append(te)
    p=pd.concat(predictions,ignore_index=True)
    return {"folds":folds,"pooled":{m:classification(p.severe,p[m])
                                  for m in ("SYMBOL_PRIOR",*models)},
            "new_holdout":False,"approved_live":False}


def run(raw,result,train):
    bull=csv(result,"research/oos_trades.csv")
    bull["family"]=bull.strategy.map({"LOGISTIC":"BULL_LOGISTIC","TREND_RULE":"BULL_TREND"})
    bear=csv(result,"research/regime_challenger/bear_oos_trades.csv")
    bear["family"]=bear.candidate_family
    events=normalize_keys(pd.concat([bull,bear.drop(columns="candidate_family")],ignore_index=True))
    if events.family.value_counts().to_dict()!={k:v[1] for k,v in FAMILIES.items()}:
        raise ValueError("UNEXPECTED_CANDIDATE_COUNTS")
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            dest=root/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(blob)
        market=root/"market"; features=root/"features"
        context=train.context_frame(market)
        spy=train.load_bars(train.market_file(market,"SPY")).close
        bars,frames={},{}
        for s in sorted(events.symbol.unique()):
            bars[s]=train.load_bars(train.market_file(market,s))
            frames[s]=train.feature_frame(s,market,features,context,20.).join(
                trailing_diagnostics(bars[s].close,spy))
        data=join_signal_features(events,frames)
        p=pd.DataFrame([path_from_ohlc(bars[x.symbol],x) for x in data.itertuples(index=False)])
        data=pd.concat([data.reset_index(drop=True),p],axis=1)
        crosscheck_count=0;crosscheck_assets=0;max_rel=0.
        for name,blob in result.items():
            if not name.startswith("research/factor_lineage/") or not name.endswith(".csv.gz") or "_repaired" in name:
                continue
            symbol=Path(name).name.split(".")[0].upper()
            d=pd.read_csv(io.BytesIO(gzip.decompress(blob)))
            ref=d.set_index(pd.to_datetime(d.session,errors="raise")).daily20_adjusted_close
            real=train.load_bars(train.market_file(market,symbol)).close
            if not ref.index.is_unique or not ref.index.isin(real.index).all():
                raise ValueError("CLOSE_LINEAGE_DATE_MISMATCH")
            real=real.reindex(ref.index)
            if not np.allclose(real,ref,rtol=1e-11,atol=1e-10,equal_nan=True):
                raise ValueError("CLOSE_LINEAGE_VALUE_MISMATCH")
            max_rel=max(max_rel,float(((real-ref).abs()/ref.abs()).max()))
            crosscheck_assets+=1;crosscheck_count+=len(ref)
        if crosscheck_assets!=25 or crosscheck_count!=59150:
            raise ValueError("CLOSE_LINEAGE_COUNT_MISMATCH")
        calendar=spy.index
    if int(data[list(FEATURES)].notna().sum().sum())!=len(data)*len(FEATURES):
        raise ValueError("ORIGINAL_FEATURE_COVERAGE_INCOMPLETE")
    port=csv(result,"research/portfolio_executions.csv")
    regime=csv(result,"research/regime_challenger/regime_executions.csv")
    output=[]
    for name,(prefix,count) in FAMILIES.items():
        candidate=data.loc[data.family.eq(name)].copy()
        ledger=port if name.startswith("BULL") else regime
        for cost in COSTS:
            ex=ledger.loc[ledger.scenario.eq(f"{prefix}__ALL_20__POS5__COST{cost}BP")]
            filled,_=match_executions(candidate,ex)
            if filled.empty:
                raise ValueError("EMPTY_FILLED_COHORT")
            for selection,frame in (("CANDIDATE",candidate),("FILLED",filled)):
                is_filled=selection=="FILLED"
                output.append({"family":name,"cost_bp":cost,"selection":selection,
                    "excursions":excursion_groups(frame,cost,is_filled),
                    "policies":[policy(frame,d,t,cost,is_filled) for d in DAYS for t in THRESHOLDS]})
    return {"schema":"kalman-exact-ohlc-exit-v1","research_only":True,"approved_live":False,
        "production_writes":False,"new_holdout":False,"portfolio_resimulated":False,
        "source_finality_certified":False,"asof":ASOF,
        "input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
        "candidate_count":len(data),"full_feature_values":int(data[list(FEATURES)].notna().sum().sum()),
        "gross_label_max_abs_error":float(data.gross_label_abs_error.max()),
        "close_lineage_assets":crosscheck_assets,"close_lineage_rows":crosscheck_count,
        "close_lineage_max_relative_error":max_rel,"groups":output,"full_risk":full_risk(data,calendar),
        "limitations":["OHLC from the pinned archive, not independent official price certification.",
            "Actual bar high and low are observed but their intraday sequence is unknown.",
            "Fixed single-checkpoint next-open alternative; same entry cohort and no cash-ledger reallocation.",
            "Inspected historical data; no threshold selection or independent confirmation."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    report=run(load_archive(a.data,"data"),load_archive(a.results,"results"),load_original(a.original_source))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("EXACT_OHLC_RESEARCH_ONLY",report["candidate_count"],report["full_feature_values"])
