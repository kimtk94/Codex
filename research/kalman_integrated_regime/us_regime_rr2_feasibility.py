#!/usr/bin/env python3
"""Regime-aware geometric feasibility and realized trades with HARD net R:R>=2.

This is a pre-registered risk-geometry sensitivity experiment, NOT searching
historical returns for an optimum. All three candidates are fixed by algebra
before running this script. No live policy changes; source SIP 15m stays on
ephemeral runner; only aggregate artifacts are uploaded.

Class-unweighted price / price+volume signals are fitted prior-year only.
Risk plan uses ATR14 through signal day, 09:45 next session entry approximation,
30bps all-in roundtrip cost, maximum 3% gross stop / 8% gross target,
and minimum planned net reward:risk >=2.0. Reject otherwise.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_hold124 import (
    SYMBOLS, ARMS, HORIZONS, make_signal_panels,
)
from research.kalman_integrated_regime.us_multisymbol_volume_screen import build_daily_rows
from research.kalman_integrated_regime.us_regime_rr_audit import spy_market_states
from research.kalman_integrated_regime.us_regime_rr_entry_gate import (
    entry_plan, simulate, MIN_NET_RR, trailing_atr_by_signal_close, ROUNDTIP_COST,
)

# These geometries are proposed for COVERAGE and risk feasibility, not
# historical profit selection. All must pass the *same* min 2.0 net R:R gate.
POLICIES = {
    "BASE_STOP125_TP300": {"stop_atr_mult":1.25, "target_atr_mult":3.00},
    "MODERATE_STOP100_TP250": {"stop_atr_mult":1.00, "target_atr_mult":2.50},
    "TIGHT_STOP075_TP225": {"stop_atr_mult":0.75, "target_atr_mult":2.25},
}
GATES = ("MIN_NET_RR_GATE", "BULL_PLUS_NET_RR_GATE")
REGIMES=("BULL","BEAR","TRANSITION")


def analytical_atr_band(stop_mult,target_mult,*,cost=ROUNDTIP_COST):
    """Solve exact net-RR >=2 and risk-distance upper bounds before outcomes."""
    diff=target_mult-MIN_NET_RR*stop_mult
    if diff<=0: raise ValueError("IMPOSSIBLE_MULTIPLIERS_TO_PASS")
    lower_rr=cost*(1+MIN_NET_RR)/diff
    low=max(lower_rr,.005/stop_mult)
    high=min(.03/stop_mult,.08/target_mult)
    return {
        "atr_over_entry_min":round(float(low),7),
        "atr_over_entry_max":round(float(high),7),
        "net_rr_binding_min":round(float(lower_rr),7),
        "possible":bool(low<=high),
        "note":"Geometric feasibility only; TP fill probability not implied"
    }


def quantiles(values):
    v=np.asarray(values,dtype=float)
    return ({str(q):round(float(np.quantile(v,q)),7) for q in (.1,.25,.5,.75,.9)}
            if len(v) else None)


def preentry_counters(dates,flags,meta,paths,ticker,policy):
    """Independent ex-ante signal opportunity counts, not selected executions."""
    reasons={}
    by_regime={r:{"signal":0,"pass":0,"rejected":0} for r in REGIMES}
    valid_rr=[]
    relative_atr=[]
    widths=[]
    for day,go,m in zip(dates,flags,meta):
        if not go: continue
        reg=m["regime"]
        if reg not in REGIMES:raise ValueError("MARKET_STATE_NOT_KNOWN")
        by_regime[reg]["signal"]+=1
        path=paths[(ticker,pd.Timestamp(day))]
        if len(path)<2 or m["atr"] is None:
            reason="MISSING_ATR_OR_ENTRY_BAR"
        else:
            entry=float(path.iloc[1].open)
            relative_atr.append(float(m["atr"])/entry)
            plan=entry_plan(entry,float(m["atr"]),**policy)
            reason=plan["reason"]
            if plan["allowed"]:
                valid_rr.append(plan["planned_net_rr"])
                widths.append({
                    "stop":plan["gross_stop_fraction"],
                    "target":plan["gross_target_fraction"]
                })
            if plan["allowed"] != (reason=="PASS"):
                raise AssertionError("PLAN_PASS_REASON_MISMATCH")
        reasons[reason]=reasons.get(reason,0)+1
        if reason=="PASS": by_regime[reg]["pass"]+=1
        else:by_regime[reg]["rejected"]+=1
    n=int(np.asarray(flags,dtype=bool).sum())
    if sum(reasons.values())!=n:
        raise AssertionError("LOST_SIGNAL_IN_FEASIBILITY")
    for group in by_regime.values():
        if group["signal"]!=group["pass"]+group["rejected"]:
            raise AssertionError("REGIME_SIGNAL_RECONCILIATION")
    return {
        "original_signal_count":n,
        "passed_pre_entry_geometry":reasons.get("PASS",0),
        "pass_fraction":round(reasons.get("PASS",0)/n,7) if n else None,
        "rejection_causes":reasons,
        "causes_are_hierarchical_first_failure":True,
        "by_market_regime_at_signal":by_regime,
        "ATR14_over_next0945_price_quantiles":quantiles(relative_atr),
        "admitted_planned_net_RR_quantiles":quantiles(valid_rr),
        "admitted_gross_stop_fraction_quantiles":quantiles([v["stop"] for v in widths]),
        "admitted_gross_target_fraction_quantiles":quantiles([v["target"] for v in widths]),
    }


def run(bars):
    panels,paths,quality=make_signal_panels(bars)
    daily,_=build_daily_rows(bars)
    market_df=spy_market_states(daily.loc[daily.symbol.eq("SPY")])
    market=dict(zip(pd.to_datetime(market_df.date_ny),market_df.market_state))
    atr=trailing_atr_by_signal_close(paths)
    # Always source from the prior COMPLETE trading session; avoid using
    # next-session intraday high/low/close for any entry gate.
    sorted_dates={sym:sorted(day for s,day in paths if s==sym) for sym in SYMBOLS}
    timeline={}
    for sym in SYMBOLS:
        idx={day:i for i,day in enumerate(sorted_dates[sym])}
        for year in (2025,2026):
            p=panels[(sym,year)]
            metadata=[]
            for date in p["dates"]:
                d=pd.Timestamp(date)
                if d not in idx or idx[d]==0:
                    raise ValueError("UNKNOWN_PRE_ENTRY_PRIOR_SESSION")
                prev=sorted_dates[sym][idx[d]-1]
                reg=market.get(prev,"UNAVAILABLE")
                if reg not in REGIMES:
                    raise ValueError("SPY_MARKET_STATE_UNAVAILABLE")
                metadata.append({"atr":atr.get((sym,prev)),"regime":reg})
            timeline[(sym,year)]=metadata
    by_symbol={}
    portfolios={}
    for year in (2025,2026):
        marks={}
        for symbol in SYMBOLS:
            panel=panels[(symbol,year)]
            meta=timeline[(symbol,year)]
            year_records={}
            for arm,signals in panel["signals"].items():
                arms={}
                for policy_name,kw in POLICIES.items():
                    candidates=preentry_counters(panel["dates"],signals,meta,paths,symbol,kw)
                    horizons={}
                    for horizon in HORIZONS:
                        variants={}
                        for gate in GATES:
                            result=simulate(
                                panel["dates"],signals,meta,paths,symbol,horizon,gate,
                                plan_multipliers=kw,
                            )
                            marks[(symbol,arm,policy_name,horizon,gate)]=result["_marks"]
                            variants[gate]={k:v for k,v in result.items() if not k.startswith("_")}
                            if result["mean_planned_net_rr"] is not None and result["mean_planned_net_rr"]<MIN_NET_RR-1e-6:
                                raise AssertionError("FORBIDDEN_RR_LESS_THAN_2")
                            if result["gate_counts"]["failed_rr"] and not result["gate_counts"]["rejected_by_reason"]:
                                raise AssertionError("REJECTION_REASON_NOT_REPORTED")
                        horizons[str(horizon)]=variants
                    arms[policy_name]={"opportunity_feasibility":candidates,
                                       "by_horizon":horizons}
                year_records[arm]=arms
            by_symbol.setdefault(symbol,{})[str(year)]=year_records
        for arm in ARMS:
            for policy_name in POLICIES:
                for horizon in HORIZONS:
                    for gate in GATES:
                        arr=np.stack([marks[(sym,arm,policy_name,horizon,gate)]
                                      for sym in SYMBOLS],axis=0)
                        wealth=arr.mean(axis=0)
                        peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
                        portfolios.setdefault(str(year),{}).setdefault(arm,{}).setdefault(
                            policy_name,{}).setdefault(str(horizon),{})[gate]={
                                "return_pct":round(float((wealth[-1]-1)*100),6),
                                "mdd_marked_eod_pct":round(float(np.min(wealth/peak-1)*100),6),
                                "initial_20_percent_per_symbol_no_rebalance":True,
                            }
    return {
        "schema":"kalman-regime-netRR2-geometry-feasibility-v1",
        "status":"RESEARCH_ONLY_NO_TRADE_PROMOTION",
        "hard_minimum_net_RR":MIN_NET_RR,
        "roundtrip_cost_fraction":ROUNDTIP_COST,
        "research_policies":POLICIES,
        "ex_ante_geometric_ATR_to_entry_bands":{
            k:analytical_atr_band(v["stop_atr_mult"],v["target_atr_mult"])
            for k,v in POLICIES.items()},
        "all_candidates_require_min_net_RR_2":True,
        "candidate_policy_selected_from_trade_returns":False,
        "2025_2026_not_fresh_out_of_sample":True,
        "by_symbol":by_symbol,
        "portfolio_initial20_nonrebalanced":portfolios,
        "data_qa":quality,
        "no_live_or_broker_change":True,
        "decision":"HOLD",
        "warnings":[
            "Geometric R:R is neither the probability of target-first nor proof of positive expectancy.",
            "A tighter ATR stop can raise simulated stop-out probability; compare realized expected R, stop-gap exits, and MDD.",
            "Three variants in previously used 2025/2026 history are exploratory; do NOT pick the best post-hoc configuration as LIVE.",
            "Volatility and trend Regime are separate research concepts from trade profitability.",
            "First failure reason suppresses lower-priority failures: not a count of all violated conditions.",
            "Stop/target and entry at historical 15m prices may differ from actual broker fills.",
            "SIP source remains private and licensed; artifacts contain aggregates only.",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-bars",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=run(pd.read_parquet(a.input_bars))
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    compact={
        sym:{year:{
          arm:{policy:{
            "feasibility":obj["opportunity_feasibility"],
            "one_day_netRR2":obj["by_horizon"]["1"]["MIN_NET_RR_GATE"],
          } for policy,obj in arms.items()}
          for arm,arms in rec.items()}
        for year,rec in years.items()}
        for sym,years in result["by_symbol"].items()
    }
    print("NETRR2_FEASIBILITY "+json.dumps(
        {"status":result["status"],"by_ticker":compact,
         "portfolio":result["portfolio_initial20_nonrebalanced"],
         "no_live":True},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
