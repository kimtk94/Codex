"""Exact original cash simulation of fixed reduced-risk arms; no live writes."""
import argparse
import json
from pathlib import Path
import tempfile

import pandas as pd

from outcome_profile import ARCHIVES, load_archive, load_original
from regime_cash_replay import CORE, old_tables, audit_original
from risk_pilot import features_and_events, annual_split, admissible, fit_fold, fixed_arms

def replay(payload, prices, portfolio):
    frame, cal = features_and_events(payload)
    bull = frame.loc[frame.family.eq("BULL_LOGISTIC")]
    predicted = []
    for year in (2025,2026):
        tr,te,_ = annual_split(bull,cal,year)
        if not admissible(tr,te):
            raise ValueError("MISSING_EXPECTED_BULL_FOLD")
        predicted.append(fit_fold(tr,te)[0])
    p = pd.concat(predicted,ignore_index=True)
    if len(p)!=254 or p.signal_date.nunique()!=167:
        raise ValueError("FROZEN_PILOT_COVERAGE")
    sessions=portfolio.validate_sessions(prices)
    state=portfolio.market_state(prices)
    def simulate(f,cost):
        events=portfolio.prepared_events(f,prices,state,strategy="LOGISTIC",excluded=set())
        return portfolio.simulate(events,prices,sessions,strategy="LOGISTIC",cohort="ALL_20",
                                  max_positions=5,allocation=.2,round_trip_cost_bps=cost)
    original, fills, _=simulate(bull,20)
    check=audit_original(original,fills,"LOGISTIC__ALL_20__POS5__COST20BP",
                         old_tables(payload)["portfolio"])
    # All challenger arms use the same 2025+ dates, including idle cash days.
    reports=[]
    for cost in (20,40,80):
        for name,mask in fixed_arms(p).items():
            curve, fills, skips=simulate(p.loc[mask],cost)
            curve=curve.loc[curve.index>=pd.Timestamp("2025-01-01")]
            reports.append({"arm":name,"cost_bp":cost,"candidates":int(mask.sum()),
                "fills":len(fills),"skips":skips,**portfolio.performance(curve)})
    return {"schema":"kalman-reduced-risk-cash-replay-v1","research_only":True,
            "new_holdout":False,"production_writes":False,"approved_live":False,
            "source_finality_certified":False,"input_sha256":{k:v[2] for k,v in ARCHIVES.items()},
            "baseline_original_replay":check,"evaluated_candidates":len(p),"scenarios":reports,
            "limitations":["Inspected retrospective candidate stream; no prospective validation.",
              "Fixed archived adjusted prices; source and listing certification HOLD.",
              "Candidate filters can change capital utilization; no exposure-matched portfolio claim."]}

def main():
    p=argparse.ArgumentParser()
    for name in ("data","results","original-source","out"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    raw,payload=load_archive(a.data,"data"),load_archive(a.results,"results")
    train=load_original(a.original_source)
    import portfolio
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for name,blob in raw.items():
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(blob)
        prices={s:train.load_bars(train.market_file(root/"market",s))[["open","close"]]
                for s in CORE+["^VIX","GLD"]}
        report=replay(payload,prices,portfolio)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("REDUCED_RISK_CASH_REPLAY_RESEARCH_ONLY",len(report["scenarios"]))

if __name__=="__main__":
    main()
