#!/usr/bin/env python3
"""Research-only *pre-entry* R:R enforcement with Bull-regime gate.

This module actually REFUSES entries with poor ex ante net reward:risk.
All parameters are hypotheses fixed before looking at this experiment:
- Signal after session T RTH close, class-unweighted price-only vs +RVOL;
- provisional market regime from SPY completed T RTH close, never P&L;
- at T+1 09:45 New York (second 15m RTH bar OPEN) entry is conditional;
- stop = entry - 1.25 * trailing ATR14 (completed at T close);
- take = entry + 3.00 * ATR14;
- pass only if net (take/entry - 1 - .003) /
  (1 - stop/entry + .003) >= 2.0;
- stop width between 0.5% and 3%; target width <=8%;
- optional Bull-only filter, no averaging down / pyramiding / overlap;
- +3/-3 fixed R:R=0.82 under 30bps is deliberately NOT approved.
- 1/2/4 NYSE sessions max, stop-first for ambiguous intraday bars;
  gap-through-stop executed at observed bar open; 30bps roundtrip.
- same test sessions across all arms and comparisons; all returns OOS
  only in a *mechanical per-year fit* sense, NOT pristine held-out research.

No broker orders, no production risk settings, no LIVE changes. Historical
open-to-fill realism, spreads and actual fees have not been validated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_hold124 import (
    SYMBOLS, HORIZONS, ARMS, make_signal_panels, SIDE_COST,
)
from research.kalman_integrated_regime.us_multisymbol_volume_screen import build_daily_rows
from research.kalman_integrated_regime.us_regime_rr_audit import spy_market_states

STOP_ATR_MULT = 1.25
TARGET_ATR_MULT = 3.0
MIN_NET_RR = 2.0
MIN_STOP_FRAC = .005
MAX_STOP_FRAC = .03
MAX_TARGET_FRAC = .08
ROUNDTIP_COST = 2 * SIDE_COST
VARIANTS = ("ORIGINAL_SIGNAL_DYNAMIC_EXITS", "MIN_NET_RR_GATE", "BULL_PLUS_NET_RR_GATE")


def trailing_atr_by_signal_close(paths):
    """14 completed NYSE RTH true ranges incl current signal day's close."""
    records=[]
    for (sym,day),bars in paths.items():
        records.append((sym,pd.Timestamp(day),float(bars.iloc[0].open),
                        float(bars.high.max()),float(bars.low.min()),
                        float(bars.iloc[-1].close)))
    frame=pd.DataFrame(records,columns=["symbol","date_ny","open","high","low","close"])
    if frame.empty or frame.duplicated(["symbol","date_ny"]).any():
        raise ValueError("INVALID_ATR_SOURCE")
    out={}
    for sym,g in frame.groupby("symbol"):
        g=g.sort_values("date_ny").copy()
        prev=g.close.shift(1)
        tr=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1)
        atr=tr.rolling(14,min_periods=14).mean()
        for day,v in zip(g.date_ny,atr):
            if np.isfinite(v) and v>0:
                out[(sym,pd.Timestamp(day))]=float(v)
    return out


def entry_plan(entry,atr,*,side_cost=SIDE_COST):
    """Prior-session ATR + *observed at 09:45* opening price; never future path."""
    if not (np.isfinite(entry) and np.isfinite(atr)) or entry<=0 or atr<=0:
        raise ValueError("INVALID_PLAN_PRICE_OR_ATR")
    stop=entry-STOP_ATR_MULT*atr
    target=entry+TARGET_ATR_MULT*atr
    if stop<=0 or not np.isfinite(stop+target):
        raise ValueError("NONPOSITIVE_STOP")
    raw_reward=(target-entry)/entry
    raw_risk=(entry-stop)/entry
    net_reward=raw_reward-2*side_cost
    net_risk=raw_risk+2*side_cost
    ratio=net_reward/net_risk
    allowed=(net_reward>0 and ratio>=MIN_NET_RR
             and MIN_STOP_FRAC<=raw_risk<=MAX_STOP_FRAC
             and raw_reward<=MAX_TARGET_FRAC)
    if net_reward<=0:
        reason="COST_EXCEEDS_TARGET"
    elif ratio<MIN_NET_RR:
        reason="NET_RR_BELOW_MINIMUM"
    elif raw_risk<MIN_STOP_FRAC:
        reason="STOP_TOO_TIGHT"
    elif raw_risk>MAX_STOP_FRAC:
        reason="STOP_TOO_WIDE"
    elif raw_reward>MAX_TARGET_FRAC:
        reason="TARGET_TOO_FAR"
    else:
        reason="PASS"
    return {"entry":float(entry),"stop":float(stop),"target":float(target),
            "gross_stop_fraction":float(raw_risk),
            "gross_target_fraction":float(raw_reward),
            "planned_net_rr":float(ratio),
            "net_winner_fraction":float(net_reward),
            "net_planned_stop_fraction":float(net_risk),
            "breakeven_win_fraction":float(1/(1+ratio)) if ratio>0 else None,
            "allowed":bool(allowed),"reason":reason}


def exit_for_session(bars,start,stop,target):
    """Check from entry bar at 09:45; later days from regular first bar."""
    for bar in bars.iloc[start:].itertuples(index=False):
        op,lo,hi=float(bar.open),float(bar.low),float(bar.high)
        if op<=stop: return op,"STOP_GAP"
        if op>=target: return target,"TARGET_LIMIT"
        if lo<=stop and hi>=target: return stop,"BOTH_HIT_STOP_FIRST"
        if lo<=stop: return stop,"STOP"
        if hi>=target: return target,"TARGET"
    return None,None


def simulate(dates,signals,meta,paths,ticker,horizon,variant):
    if variant not in VARIANTS or horizon not in HORIZONS:
        raise ValueError("UNKNOWN_VARIANT_OR_HORIZON")
    if not (len(dates)==len(signals)==len(meta)):
        raise ValueError("UNPAIRED_SIGNALS_OR_REGIME")
    dates=[pd.Timestamp(d) for d in dates]
    if len(set(dates))!=len(dates) or dates!=sorted(dates):
        raise ValueError("BAD_TRADE_DATES")
    signal=np.asarray(signals,dtype=bool)
    equity=1.0
    mark_trace=[]
    current=None
    trades=[]
    counters={"signal":int(signal.sum()),"failed_rr":0,"blocked_regime":0,
              "blocked_overlap":0,"invalid_source":0,"tail_rejected":0}
    last_entry=len(dates)-max(HORIZONS)
    for i,day in enumerate(dates):
        key=(ticker,day)
        if key not in paths: raise ValueError("MISSING_RTH_SESSION")
        path=paths[key]
        if current is None and signal[i]:
            if i>last_entry:
                counters["tail_rejected"]+=1
            elif len(path)<2 or meta[i]["atr"] is None:
                counters["invalid_source"]+=1
            else:
                plan=entry_plan(float(path.iloc[1].open),float(meta[i]["atr"]))
                if variant!="ORIGINAL_SIGNAL_DYNAMIC_EXITS" and not plan["allowed"]:
                    counters["failed_rr"]+=1
                elif variant=="BULL_PLUS_NET_RR_GATE" and meta[i]["regime"]!="BULL":
                    counters["blocked_regime"]+=1
                else:
                    # Ungated historical baseline is comparison ONLY, not an
                    # approved strategy. Every gated simulated entry must
                    # satisfy the user-required >=2.0 NET R:R hard limit.
                    if variant!="ORIGINAL_SIGNAL_DYNAMIC_EXITS" and (
                        not plan["allowed"] or plan["planned_net_rr"] < MIN_NET_RR
                    ):
                        raise AssertionError("GATED_TRADE_FAILED_MIN_NET_RR")
                    current={"index":i,"entry_day":str(day.date()),
                             "entry_regime":meta[i]["regime"],
                             "plan":plan,"mark":1.}
        elif current is not None and signal[i]:
            counters["blocked_overlap"]+=1
        if current is not None:
            plan=current["plan"]
            elapsed=i-current["index"]+1
            start=1 if i==current["index"] else 0
            fill,reason=exit_for_session(path,start,plan["stop"],plan["target"])
            finish=fill is not None or elapsed>=horizon
            if finish:
                price=float(fill if fill is not None else path.iloc[-1].close)
                reason=reason or "TIME_CLOSE"
                factor=price/plan["entry"]-ROUNDTIP_COST
                if factor<=0: raise ValueError("NONPOSITIVE_EXIT_WEALTH")
                equity*=factor/current["mark"]
                trades.append({"net":factor-1,"regime":current["entry_regime"],
                               "rr":plan["planned_net_rr"],
                               "realized_R":(factor-1)/plan["net_planned_stop_fraction"],
                               "reason":reason,"sessions_held":elapsed})
                current=None
            else:
                factor=float(path.iloc[-1].close)/plan["entry"]-SIDE_COST
                if factor<=0: raise ValueError("NONPOSITIVE_MARK")
                equity*=factor/current["mark"]
                current["mark"]=factor
        mark_trace.append(equity)
    if current is not None:raise AssertionError("UNCLOSED_POSITION")
    mark=np.asarray(mark_trace)
    peak=np.maximum.accumulate(np.r_[1.,mark])[1:]
    nums=np.asarray([t["net"] for t in trades],dtype=float)
    group={}
    for state in ("BULL","BEAR","TRANSITION"):
        sub=[t for t in trades if t["regime"]==state]
        r=np.asarray([x["net"] for x in sub],dtype=float)
        group[state]={"trades":len(sub),
                      "win_rate":round(float((r>0).mean()),6) if len(r) else None,
                      "mean_net_trade_pct":round(float(r.mean()*100),6) if len(r) else None,
                      "compounded_trade_chain_pct":round(float((np.prod(1+r)-1)*100),6) if len(r) else None,
                      "mean_planned_rr":round(float(np.mean([x["rr"] for x in sub])),6) if sub else None,
                      "realized_expectancy_R":round(float(np.mean([x["realized_R"] for x in sub])),6) if sub else None,
                      "mean_winner_net_pct":round(float(100*np.mean([x["net"] for x in sub if x["net"]>0])),6) if any(x["net"]>0 for x in sub) else None,
                      "mean_loser_net_pct":round(float(100*np.mean([x["net"] for x in sub if x["net"]<0])),6) if any(x["net"]<0 for x in sub) else None,
                      "not_a_calendar_portfolio_return":True}
    return {
        "trades":len(trades),"signal_count":int(signal.sum()),
        "cum_return_pct":round(float((equity-1)*100),6),
        "mdd_eod_pct":round(float((mark/peak-1).min()*100),6),
        "win_rate":round(float((nums>0).mean()),6) if len(nums) else None,
        "average_net_trade_pct":round(float(nums.mean()*100),6) if len(nums) else None,
        "mean_planned_net_rr":round(float(np.mean([t["rr"] for t in trades])),6) if trades else None,
        "realized_expectancy_R":round(float(np.mean([t["realized_R"] for t in trades])),6) if trades else None,
        "gate_counts":counters,
        "by_market_regime":group,
        "_marks":mark,
    }


def run(bars):
    panels,paths,qa=make_signal_panels(bars)
    daily,_=build_daily_rows(bars)
    regime_df=spy_market_states(daily.loc[daily.symbol.eq("SPY")])
    regime_map=dict(zip(pd.to_datetime(regime_df.date_ny),regime_df.market_state))
    atr_map=trailing_atr_by_signal_close(paths)
    report={}
    portfolios={}
    for year in (2025,2026):
        marks={}
        for ticker in SYMBOLS:
            panel=panels[(ticker,year)]
            # make_signal_panels records trade dates only; predecessor from
            # symbol-specific sorted complete-session dates, never T+1.
            all_dates=sorted(key[1] for key in paths if key[0]==ticker)
            idx={d:i for i,d in enumerate(all_dates)}
            meta=[]
            for trade_date in panel["dates"]:
                day=pd.Timestamp(trade_date)
                if day not in idx or idx[day]==0:
                    raise ValueError("NO_SIGNAL_PREDECESSOR")
                prior=all_dates[idx[day]-1]
                reg=regime_map.get(prior,"UNAVAILABLE")
                if reg not in ("BULL","BEAR","TRANSITION"):
                    raise ValueError("MISSING_PRIOR_MARKET_REGIME")
                meta.append({"atr":atr_map.get((ticker,prior)),"regime":reg})
            ticker_output={}
            for arm,signals in panel["signals"].items():
                variants={}
                for h in HORIZONS:
                    h_summary={}
                    for variant in VARIANTS:
                        x=simulate(panel["dates"],signals,meta,paths,ticker,h,variant)
                        marks[(ticker,arm,h,variant)]=x["_marks"]
                        h_summary[variant]={k:v for k,v in x.items() if not k.startswith("_")}
                    variants[str(h)]=h_summary
                ticker_output[arm]=variants
            report.setdefault(ticker,{})[str(year)]=ticker_output
        for arm in ARMS:
            for h in HORIZONS:
                for variant in VARIANTS:
                    arr=np.stack([marks[(ticker,arm,h,variant)] for ticker in SYMBOLS])
                    mark=arr.mean(axis=0)
                    peak=np.maximum.accumulate(np.r_[1.,mark])[1:]
                    portfolios.setdefault(str(year),{}).setdefault(arm,{}).setdefault(str(h),{})[variant]={
                        "cumulative_return_pct":round(float((mark[-1]-1)*100),6),
                        "mdd_marked_eod_pct":round(float((mark/peak-1).min()*100),6),
                        "initial_20_pct_capital_sleeves_no_rebalance":True,
                    }
    return {
        "schema":"kalman-regime-conditioned-exante-entry-rr-gate-v1",
        "status":"RESEARCH_ONLY_NO_LIVE_CHANGES",
        "rule":"09:45 fill, trailing prior-session ATR14; stop1.25xATR, target3xATR; NET_RR >=2.0 mandatory for gated trade variants; optional SPY BULL gate",
        "min_net_reward_risk":MIN_NET_RR,
        "tp_sl_from":"completed prior session ATR, conditional fill at next 09:45",
        "roundtrip_cost_fraction":ROUNDTIP_COST,
        "trading_horizons_sessions":list(HORIZONS),
        "variants":list(VARIANTS),
        "ungated_original_is_comparison_only_not_admissible":True,
        "min_net_rr_applies_to":["MIN_NET_RR_GATE","BULL_PLUS_NET_RR_GATE"],
        "entry_policy_hard_veto":True,
        "by_ticker":report,
        "initial_equalweight_five_sleeve_portfolio":portfolios,
        "source_qa":qa,
        "risk_warnings":[
            "2.0 planned NET reward:risk is required before every entry in gated variants, but does NOT imply positive expectancy or a validated TP-before-SL probability.",
            "No attempt to force unrealistic profit targets; invalid stop distances and >8% projected target cause trade rejection.",
            "The first 15-minute regular-session bar is deliberately skipped; entry assumed at 09:45 second bar open.",
            "SPY trend regime uses only prior day's complete close, independent of future trade returns.",
            "2025/2026 historical data repeatedly inspected; no pristine prospective OOS or live promotion.",
            "15m bar OHLC ambiguity resolved stop-first; gaps execute at observed opening of later bars.",
            "Slippage/fill realism, intrabar MDD, tax, financial impact, position correlation unvalidated.",
        ],
        "live_changed":False,
        "promotion":"HOLD"
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-bars",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=run(pd.read_parquet(a.input_bars))
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    summary={
        year:{arm:{h:{variant:val for variant,val in variants.items()}
                  for h,variants in hh.items()}
              for arm,hh in arm_data.items()}
        for year,arm_data in result["initial_equalweight_five_sleeve_portfolio"].items()
    }
    print("ENTRY_RR_GATE_BACKTEST "+json.dumps(
        {"status":result["status"],"portfolio":summary,"live":result["live_changed"]},
        ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
