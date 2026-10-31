#!/usr/bin/env python3
"""Private COIN matched-signal fill-cost repricing and month-block uncertainty.

Research-only. Requires original PIT candidate list and private SIP 15m bars.
Never publishes dates, individual returns, OHLC, predictions or fill prices.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from random import Random

from coin_structure import ARMS, HORIZONS, geometry, simulate, required_target
from coin_signal_replay import EXPECTED, validate_entries

COSTS=(.003,.005,.010)
BOOTSTRAPS=4000


def reprice_plan(base, arm, fee):
    """Cost increase must reprice the target *before* entry, or refuse entry."""
    if not base["pass"]:
        return None
    stop = base["stop_pct"]
    target = (base["target_pct"] if arm == "ORL_PRIOR20_HIGH"
              else required_target(stop,fee))
    if target > .08 + 1e-12 or (target-fee)/(stop+fee) < 2 - 1e-9:
        return None
    return stop,target


def percentile(sorted_values,quantile):
    if not sorted_values:
        return None
    i=(len(sorted_values)-1)*quantile
    k=int(i)
    if k==len(sorted_values)-1:
        return sorted_values[k]
    return sorted_values[k]*(1-(i-k))+sorted_values[k+1]*(i-k)


def month_block_interval(trades, sessions, *, seed, iterations=BOOTSTRAPS):
    """Resample MONTH groups, not isolated trades. Descriptive, not pristine OOS."""
    if not trades:
        return {"months":0,"bootstrap95_mean_R":None,
                "leave_best_trade_out_mean_R":None,
                "no_iid_independence_claim":True}
    monthly=defaultdict(list)
    for trade in trades:
        key=sessions[trade["entry_index"]]["date"][:7]
        monthly[key].append(trade["realized_R"])
    n=len(trades)
    value=[t["realized_R"] for t in trades]
    leave=(sum(value)-max(value))/(n-1) if n>1 else None
    k=len(monthly)
    ci=None
    if k>=3:
        rng=Random(seed)
        blocks=list(monthly.values())
        means=[]
        for _ in range(iterations):
            arr=[v for _ in range(k) for v in blocks[rng.randrange(k)]]
            means.append(sum(arr)/len(arr))
        means.sort()
        ci=[round(percentile(means,.025),6),round(percentile(means,.975),6)]
    return {"months":k,"bootstrap95_mean_R":ci,
            "leave_best_trade_out_mean_R":round(leave,6) if leave is not None else None,
            "no_iid_independence_claim":True}


def stress(sessions, ledger, baseline_rows, *, expected=EXPECTED):
    observed=validate_entries(ledger,sessions,expected=expected)
    baseline={(r["year"],r["arm"],r["hold_sessions"]):r
              for r in baseline_rows}
    grid={(y,a,h) for y in expected for a in ARMS for h in HORIZONS}
    if set(baseline)!=grid:
        raise ValueError("MISSING_OR_DUPLICATE_BASELINE_CELLS")
    out=[]
    for year in sorted(expected):
        cohort=[i for i,r in observed if int(r["entry_date"][:4])==year]
        for arm in ARMS:
            exante=[]
            for idx in cohort:
                open_0945=sessions[idx]["bars"][1]["o"]
                g=geometry(open_0945,sessions[idx]["bars"][0]["l"],
                           sessions[idx-1]["low"],
                           max(x["high"] for x in sessions[idx-20:idx]),arm)
                if g["pass"]:
                    exante.append((idx,g))
            for fee in COSTS:
                plans=[]
                declined_cost=0
                for idx,base in exante:
                    plan=reprice_plan(base,arm,fee)
                    if plan is None:
                        declined_cost+=1
                        continue
                    plans.append((idx,*plan))
                for horizon in HORIZONS:
                    used=[]
                    last_exit=-1
                    overlap=right_censored=0
                    for idx,sl,tp in plans:
                        if idx+horizon>len(sessions):
                            right_censored+=1
                            continue
                        if idx<=last_exit:
                            overlap+=1
                            continue
                        tr=simulate(sessions,idx,horizon,sl,tp,fee=fee)
                        used.append(tr)
                        last_exit=tr["exit_index"]
                    if len(used)+overlap+right_censored != len(plans):
                        raise ValueError("COST_REPRICE_TRADE_LEDGER_ACCOUNTING")
                    n=len(used)
                    rs=[t["realized_R"] for t in used]
                    mean=round(sum(rs)/n,6) if n else None
                    if fee==.003:
                        reference=baseline[(year,arm,horizon)]
                        if (n!=reference["trades"] or len(plans)!=reference["structural_pass"]
                                or mean!=reference["mean_R"]):
                            raise ValueError("REPRICE_30BP_BASELINE_PARITY_FAILED")
                    uncertainty=month_block_interval(
                        used,sessions,seed=year*10000+ARMS.index(arm)*100+horizon*10+int(fee*10000))
                    gap=sum(t["reason"]=="STOP_GAP" for t in used)
                    out.append({
                        "year":year,"arm":arm,"hold_sessions":horizon,
                        "roundtrip_cost_bps":int(round(fee*10000)),
                        "original_model_signals":len(cohort),
                        "geometry_pass_at_30bp":len(exante),
                        "rejected_by_higher_cost_RR_or_target_cap":declined_cost,
                        "valid_ex_ante_after_repriced_target":len(plans),
                        "trades":n,"overlap_blocked":overlap,
                        "right_censored":right_censored,
                        "net_mean_R":mean,
                        "net_mean_pct":round(100*sum(t["net_fraction"] for t in used)/n,6) if n else None,
                        "gap_through_stop":gap,
                        "target_exits":sum(t["reason"] in ("TARGET","TARGET_GAP") for t in used),
                        "stop_exits":sum(t["reason"] in ("STOP","STOP_GAP") for t in used),
                        "time_exits":sum(t["reason"]=="TIME_CLOSE" for t in used),
                        "uncertainty":uncertainty,
                    })
    if len(out)!=len(expected)*len(ARMS)*len(HORIZONS)*len(COSTS):
        raise ValueError("REPRICE_GRID_INCOMPLETE")
    return {
        "schema":"coin-original-model-matched-month-block-and-cost-reprice-v1",
        "status":"RESEARCH_ONLY_NO_LIVE_PROMOTION",
        "live":"HOLD","original_signal_year_counts":{str(k):v for k,v in expected.items()},
        "costs_reprice_target_before_trade":True,
        "same_bar_both_barriers_stop_first":True,
        "gap_stop_observed_bar_open":True,
        "confidence_intervals_are_exploratory":True,
        "no_new_unseen_OOS":True,
        "bootstrap_resampling_unit":"NY_MONTH_OF_ENTRY",
        "bootstrap_replications":BOOTSTRAPS,
        "no_private_dates_or_trade_rows":True,
        "results":out,
    }
