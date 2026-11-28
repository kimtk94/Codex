"""Descriptive close-only trade-path analysis of the pinned result archive.

The entry open is algebraically reconstructed from the archived gross label and
terminal adjusted close, NOT an independently verified OHLC observation.
No intraday MAE/MFE, no stop execution, no prediction or portfolio counterfactual.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from outcome_profile import ARCHIVES, KEY, csv, load_archive, normalize_keys
from risk_pilot import read

SCENARIOS = {"BULL_LOGISTIC": "LOGISTIC", "BULL_TREND": "TREND_RULE",
             "BEAR_LOGISTIC": "BEAR_LOGISTIC_ONLY", "BEAR_RULE": "BEAR_RULE_ONLY"}
COUNTS = {"BULL_LOGISTIC":439,"BULL_TREND":1061,"BEAR_LOGISTIC":89,"BEAR_RULE":152}
CLOSE_COLS = ["g1","g2","g3","g4"]
NET_COLS = ["r1","r2","r3","r4"]


def close_path(close, event):
    """Require a complete exact four-close window and reconstruct the label."""
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError("INVALID_PRICE_DATES")
    window = close.loc[event.entry_date:event.exit_date]
    if (len(window)!=4 or window.index[0]!=event.entry_date
            or window.index[-1]!=event.exit_date
            or not np.isfinite(window).all() or not window.gt(0).all()):
        raise ValueError("INCOMPLETE_FOUR_SESSION_WINDOW")
    if not np.isfinite(event.gross_return) or event.gross_return<=-1:
        raise ValueError("INVALID_GROSS_LABEL")
    index = close.index.get_loc(event.entry_date)
    if index==0 or close.index[index-1]!=event.signal_date:
        raise ValueError("SIGNAL_ENTRY_SESSION_MISMATCH")
    implied_open = window.iloc[-1]/(1+event.gross_return)
    result = window.to_numpy(float)/implied_open-1
    if not np.isclose(result[-1],event.gross_return,atol=1e-12,rtol=0):
        raise ValueError("TERMINAL_LABEL_MISMATCH")
    return result


def add_net_path(frame,filled):
    x=frame.copy()
    for g,r in zip(CLOSE_COLS,NET_COLS):
        # Candidate labels use nominal cost subtraction; the cash ledger
        # uses half-cost at each side on the actual entry/exit price.
        x[r]=(1+x[g])*.999/1.001-1 if filled else x[g]-.002
    label=x.realized_return if filled else x.net_return
    if not np.allclose(x.r4,label,atol=2e-10,rtol=0):
        raise ValueError("NET_RETURN_MISMATCH")
    x["group"]=np.select([x.r4.gt(0),x.r4.le(-.05),x.r4.lt(0)],
                         ["WIN","SEVERE_LOSS","MILD_LOSS"],default="BREAKEVEN")
    x["close_mfe"]=x[CLOSE_COLS].max(axis=1).clip(lower=0)
    x["close_mae"]=x[CLOSE_COLS].min(axis=1).clip(upper=0)
    return x


def group_summary(frame):
    return {"n":len(frame),"signal_dates":int(frame.signal_date.nunique()),
            "median_net_path":[float(frame[r].median()) for r in NET_COLS],
            "median_close_sampled_mfe_gross":float(frame.close_mfe.median()),
            "median_close_sampled_mae_gross":float(frame.close_mae.median()),
            "positive_close_before_exit":int(frame[NET_COLS[:3]].max(axis=1).gt(0).sum()),
            "at_or_below_minus_2pct_before_exit":int(frame[NET_COLS[:3]].min(axis=1).le(-.02).sum()),
            "at_or_below_minus_5pct_before_exit":int(frame[NET_COLS[:3]].min(axis=1).le(-.05).sum())}


def checkpoint(frame,day,threshold):
    flag=frame[f"r{day}"].le(threshold)
    severe=frame.r4.le(-.05)
    wins=frame.r4.gt(0)
    remaining=(1+frame.g4)/(1+frame[f"g{day}"])-1
    def one(mask):
        n=int(mask.sum())
        return {"n":n,"dates":int(frame.loc[mask,"signal_date"].nunique()),
                "severe":int((mask&severe).sum()),"wins":int((mask&wins).sum()),
                "severe_rate":float(severe[mask].mean()) if n else None,
                "mean_remaining_gross_close_to_close":float(remaining[mask].mean()) if n else None}
    return {"day":day,"threshold":threshold,"flagged":one(flag),"other":one(~flag),
            "total_severe":int(severe.sum()),"total_wins":int(wins.sum()),
            "not_an_executable_exit":True}


def report(payload):
    bull=csv(payload,"research/oos_trades.csv")
    bull["family"]=bull.strategy.map({"LOGISTIC":"BULL_LOGISTIC","TREND_RULE":"BULL_TREND"})
    bear=csv(payload,"research/regime_challenger/bear_oos_trades.csv")
    bear["family"]=bear.candidate_family
    events=normalize_keys(pd.concat([bull,bear.drop(columns="candidate_family")],ignore_index=True))
    if events.family.value_counts().to_dict()!=COUNTS or events.duplicated(["family",*KEY]).any():
        raise ValueError("CANDIDATE_COUNT_OR_KEY_MISMATCH")
    prices={}
    for s in sorted(events.symbol.unique()):
        d=read(payload,"research/factor_lineage/"+s.lower()+".csv.gz")
        prices[s]=d.set_index(pd.to_datetime(d.session,errors="raise")).daily20_adjusted_close.astype(float).sort_index()
    paths=[close_path(prices[r.symbol],r) for r in events.itertuples(index=False)]
    events[CLOSE_COLS]=np.array(paths)
    port=normalize_keys(csv(payload,"research/portfolio_executions.csv"))
    regime=normalize_keys(csv(payload,"research/regime_challenger/regime_executions.csv"))
    families={}
    for f,prefix in SCENARIOS.items():
        candidate=events.loc[events.family.eq(f)]
        ledger=port if f.startswith("BULL") else regime
        execs=ledger.loc[ledger.scenario.eq(prefix+"__ALL_20__POS5__COST20BP")]
        filled=candidate.merge(execs[KEY+["realized_return"]],on=KEY,how="inner",validate="one_to_one")
        if len(filled)!=len(execs) or filled.empty:
            raise ValueError("EXECUTION_MATCH_FAILED")
        families[f]={}
        for selection,frame in (("CANDIDATES",candidate),("FILLED",filled)):
            x=add_net_path(frame,selection=="FILLED")
            families[f][selection]={"n":len(x),
                "groups":{k:group_summary(g) for k,g in x.groupby("group")},
                "fixed_checkpoints":[checkpoint(x,d,t) for d in (1,2,3) for t in (-.02,-.05)],
                "day1_minus2_by_year":{str(y):checkpoint(g,1,-.02)
                                       for y,g in x.groupby(x.signal_date.dt.year)}}
    return {"schema":"kalman-close-path-descriptive-v1","input_sha256":ARCHIVES["results"][2],
            "candidate_count":len(events),"families":families,"research_only":True,
            "approved_live":False,"production_writes":False,"new_holdout":False,
            "entry_open_independently_verified":False,"intraday_mae_mfe_available":False,
            "exit_simulation_performed":False,
            "limitations":["The entry open is reconstructed from the terminal label; no independent price proof.",
                           "Close-sampled excursions include the zero entry mark; intraday extremes are unobserved.",
                           "Checkpoint categories are descriptive fixed thresholds, not optimized trading rules.",
                           "Remaining close-to-close return is not a feasible same-close fill or portfolio replay.",
                           "Outcome groups use final labels and are retrospective; no causal or confirmatory claim."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--results",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    r=report(load_archive(a.results,"results"))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n")
    print("CLOSE_PATH_DESCRIPTIVE",r["candidate_count"])
