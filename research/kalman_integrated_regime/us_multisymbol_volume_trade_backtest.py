#!/usr/bin/env python3
"""Five-ticker, research-only, next-session matched-cost trading simulation.

This is NOT executable order code and cannot be used to modify LIVE.
Evaluates prior-year-only P vs P+RVOL models and all-days intraday long control,
with fixed next-session open/close, or conservative one-session +3%/-3%
15-minute OHLC barriers. Fee and slippage per side are explicit. No short sales,
no overnight exposure, no use of test-year labels for fitting or tuning.
Hypothesis/data already repeatedly examined: exploratory, not pristine OOS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
    PRICE, VOLUME, build_daily_rows, matched_cohorts,
)
from research.kalman_integrated_regime.us_multisymbol_microstructure import NY

FEE_PER_SIDE=0.001  # 10 basis points per side
SLIPPAGE_PER_SIDE=0.0005 # 5bp per side
TP=0.03
SL=0.03
ENTRY_THRESHOLD=0.50
MODELS={"P_unweighted":(PRICE,None),
        "V_unweighted":(PRICE+VOLUME,None),
        "P_balanced":(PRICE,"balanced"),
        "V_balanced":(PRICE+VOLUME,"balanced")}
EXIT_POLICIES=("NEXT_RTH_CLOSE","SAME_SESSION_TP3_SL3")
MODEL_PAIRED=(("P_unweighted","V_unweighted"),
              ("P_balanced","V_balanced"))


def session_paths(bars):
    """Construct only fully observed symbol/session OHLC 15m paths, fail closed."""
    cal=xcals.get_calendar("XNYS")
    x=bars.copy()
    x["ts"]=pd.to_datetime(x.candle_time_utc,utc=True)
    x["day"]=pd.to_datetime(x.ts.dt.tz_convert(NY).dt.strftime("%Y-%m-%d"))
    result={}
    for (sym,day),group in x.groupby(["market","day"]):
        if not cal.is_session(day):
            continue
        start=cal.session_open(day)
        end=cal.session_close(day)
        y=group.loc[group.ts.ge(start)&group.ts.lt(end)].sort_values("ts")
        expected=pd.date_range(start,end-pd.Timedelta(minutes=15),freq="15min")
        if not pd.DatetimeIndex(y.ts).equals(expected):
            continue
        if (y[["open","high","low","close"]].isna().any().any()
                or (y[["open","high","low","close"]]<=0).any().any()
                or (y.high<y[["open","close","low"]].max(axis=1)).any()
                or (y.low>y[["open","close"]].min(axis=1)).any()):
            raise ValueError(f"OHLC_INVALID:{sym}:{day}")
        result[(sym,pd.Timestamp(day))]=y.reset_index(drop=True)
    return result


def intraday_exit(path, policy):
    """Long entry at next RTH first bar OPEN, pessimistic same-bar stop-first."""
    if path.empty:
        raise ValueError("EMPTY_EXIT_PATH")
    op=float(path.iloc[0].open)
    close=float(path.iloc[-1].close)
    if op<=0:
        raise ValueError("NONPOSITIVE_ENTRY")
    if policy=="NEXT_RTH_CLOSE":
        return close/op-1,"EOD"
    if policy!="SAME_SESSION_TP3_SL3":
        raise ValueError("UNKNOWN_EXIT_POLICY")
    stop=op*(1-SL)
    take=op*(1+TP)
    for bar in path.itertuples(index=False):
        # gap beyond stop or take on a later 15-min bar: execute at observed
        # opening, not at imaginary superior stop/take price.
        bo=float(bar.open)
        if bo<=stop:
            return bo/op-1,"STOP_GAP"
        if bo>=take:
            return take/op-1,"TP_OPEN"
        low=float(bar.low)
        high=float(bar.high)
        if low<=stop and high>=take:
            return -SL,"AMBIGUOUS_STOP_FIRST"
        if low<=stop:
            return -SL,"STOP"
        if high>=take:
            return TP,"TAKE_PROFIT"
    return close/op-1,"EOD"


def trade_ledger(dates, signals, paths, symbol, *, policy, capital_fraction=1.,
                 fee=FEE_PER_SIDE, slip=SLIPPAGE_PER_SIDE):
    """One independent roundtrip per next-session day, cash whenever flat.

    Daily return = invested allocation × (gross open-to-exit - roundtrip cost).
    This is a linear friction approximation, with fills at shown OHLC stop/
    limit levels. Real realized slippage may differ, particularly for gaps.
    """
    if not 0<=capital_fraction<=1:
        raise ValueError("INVALID_CAPITAL_ALLOCATION")
    if fee<0 or slip<0 or fee+slip>=.1:
        raise ValueError("INVALID_FRICTION_BOUNDS")
    if len(dates)!=len(signals):
        raise ValueError("SIGNAL_NOT_DATE_ALIGNED")
    equity=1.
    peak=1.
    worst_drawdown=0.
    transactions=[]
    n_wins=0
    sum_fees=0.
    return_trace=[]
    exit_reasons={}
    for day,signal in zip(dates,signals):
        key=(symbol,pd.Timestamp(day))
        if key not in paths:
            raise ValueError(f"MISSING_COMPLETE_BAR_PATH:{symbol}:{day}")
        if not isinstance(signal,(bool,np.bool_)):
            raise ValueError("NONBOOLEAN_ENTRY")
        retn=0.
        if signal:
            gross,reason=intraday_exit(paths[key],policy)
            costs=2*(fee+slip)
            net=gross-costs
            retn=capital_fraction*net
            sum_fees+=capital_fraction*costs
            n_wins+=int(net>0)
            transactions.append(net)
            exit_reasons[reason]=exit_reasons.get(reason,0)+1
        equity*=1+retn
        peak=max(peak,equity)
        worst_drawdown=min(worst_drawdown,equity/peak-1)
        return_trace.append(retn)
    total=sum(bool(k) for k in signals)
    if total!=len(transactions):
        raise AssertionError("TRADE_COUNT_INCONSISTENT")
    if not np.isfinite(equity) or equity<=0:
        raise ValueError("EQUITY_INVALID")
    return {
        "signal_days":int(len(dates)),
        "trades":int(total),
        "exposure_days":int(total),
        "trade_rate":round(total/len(dates),6),
        "win_rate_executed":round(n_wins/total,6) if total else None,
        "average_trade_net_pct":round(100*np.mean(transactions),6) if total else None,
        "cumulative_return_pct":round(100*(equity-1),6),
        "max_drawdown_eod_pct":round(100*worst_drawdown,6),
        "cost_assumption_each_side_bps":round(10000*(fee+slip),3),
        "aggregate_friction_unit_return":round(sum_fees,6),
        "exit_reason_counts":exit_reasons,
        "no_overnight_exposure":True,
        "no_short_or_margin":True,
        "capital_fraction":capital_fraction,
    }


def annual(symbol,train,test,paths,year,*,capital_fraction=1.):
    """Exactly same dates/fees for four models and always-long control."""
    test=test.loc[test.date_ny.dt.month.le(10)&
                  test.next_session_date.dt.month.le(10)].copy()
    if len(test)<120:
        raise ValueError("INCOMPLETE_MATCHED_JAN_OCT")
    signal_dates=list(test.next_session_date)
    if len(signal_dates)!=len(set(signal_dates)):
        raise ValueError("DUPLICATE_TRADE_DAY")
    if train.next_session_date.max()>=pd.Timestamp(f"{year}-01-01"):
        raise AssertionError("TARGET_LABEL_LEAK")
    y=(train.next_session_rth_return.astype(float).to_numpy()>0).astype(int)
    if len(np.unique(y))<2:
        raise ValueError("TRAIN_ONE_CLASS")
    predictions={}
    for name,(cols,weights) in MODELS.items():
        model=make_pipeline(
            StandardScaler(),
            LogisticRegression(C=1.,max_iter=1000,class_weight=weights,random_state=42))
        model.fit(train[cols],y)
        p=model.predict_proba(test[cols])[:,1]
        predictions[name]=(p>=ENTRY_THRESHOLD)
    predictions["ALWAYS_INTRADAY_LONG"]=np.ones(len(test),dtype=bool)
    policy_results={}
    for policy in EXIT_POLICIES:
        ledger={}
        for name,decisions in predictions.items():
            ledger[name]=trade_ledger(
                signal_dates,decisions,paths,symbol,policy=policy,
                capital_fraction=capital_fraction)
        contrasts={}
        for first,last in MODEL_PAIRED:
            a,b=ledger[first],ledger[last]
            contrasts[f"{last}_minus_{first}"]={
                "return_delta_percentage_points":
                    round(b["cumulative_return_pct"]-a["cumulative_return_pct"],6),
                "mdd_delta_percentage_points":
                    round(b["max_drawdown_eod_pct"]-a["max_drawdown_eod_pct"],6),
                "trade_delta":b["trades"]-a["trades"],
            }
        policy_results[policy]={"arms":ledger,"paired_contrasts":contrasts}
    return {
        "year":year,
        "train_n":int(len(train)),
        "test_n":int(len(test)),
        "test_first_signal":str(test.date_ny.min().date()),
        "test_last_trade":str(test.next_session_date.max().date()),
        "last_available_train_outcome":str(train.next_session_date.max().date()),
        "entry_probability_cutoff":ENTRY_THRESHOLD,
        "fixed_one_session_exits":list(EXIT_POLICIES),
        "friction_per_side":{"fee":FEE_PER_SIDE,"slippage":SLIPPAGE_PER_SIDE},
        "policies":policy_results,
        "same_training_dates_same_trade_dates":True,
        "source_is_15_min_adjusted_sip":True
    }


def run(bars,*,capital_fraction=1.):
    daily,qa=build_daily_rows(bars)
    paths=session_paths(bars)
    results={}
    for sym,day in daily.groupby("symbol"):
        years={}
        for year in (2025,2026):
            tr,te=matched_cohorts(day,year)
            years[str(year)]=annual(sym,tr,te,paths,year,
                                    capital_fraction=capital_fraction)
        results[sym]=years
    return {
        "schema":"kalman-us-five-symbols-open-close-tp3sl3-cost-returns-v1",
        "status":"EXPLORATORY_BACKTEST_NO_LIVE_GO",
        "session_source_quality":qa,
        "source_feed":"Alpaca SIP adjustment=all; 15m completed RTH OHLCV",
        "symbols":list(results),
        "test":"Jan-Oct 2025 and 2026, fixed, separate per-symbol capital",
        "signal_timestamp":"prior session RTH close, next eligible RTH open",
        "trade_model":"long or cash, open to same-session close, no overnight",
        "fee_slippage_roundtrip_fraction":2*(FEE_PER_SIDE+SLIPPAGE_PER_SIDE),
        "barrier":"+3% TP/-3% SL, first touched; both in bar => stop first",
        "capital_fraction":capital_fraction,
        "by_symbol":results,
        "live_changed":False,
        "promotion":"HOLD",
        "limitations":[
            "All strategies use historical fitted signals and open price fills; execution at exact historical open is an unverified idealization.",
            "15m OHLC cannot disambiguate within-bar first touch; stop-first on both.",
            "Slippage modeled at fixed 5bp per side, not historical actual spreads/quotes.",
            "Barriers operate for one trading session only; NOT the QLD four-session rule.",
            "All-days intraday long trades daily and is NOT a continuous buy-and-hold benchmark (pays roundtrip fees every day).",
            "MDD computed using daily exit equity, not intrabar lows or leveraged exposure; no portfolio cross-ticker aggregation.",
            "Outcome and data have already been used to choose research tasks; not fresh untouched OOS.",
            "Corporate-action adjustment and trade-condition market impacts not independently audited.",
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-bars",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--capital-fraction",type=float,default=1.)
    a=p.parse_args()
    report=run(pd.read_parquet(a.input_bars),capital_fraction=a.capital_fraction)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    compact={sym:{year:{
        k:{name:{m:v[m] for m in
             ("trades","cumulative_return_pct","max_drawdown_eod_pct","win_rate_executed")}
           for name,v in pol["arms"].items()}
        for k,pol in rec["policies"].items()}
        for year,rec in years.items()}
        for sym,years in report["by_symbol"].items()}
    print("FIVE_TICKER_TRADE_BACKTEST "+json.dumps(compact,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
