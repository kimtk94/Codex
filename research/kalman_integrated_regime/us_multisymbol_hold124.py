#!/usr/bin/env python3
"""Research-only one/two/four NYSE session holding window: long/cash, no overlap.

Use only prior-year fitted price-3 or price+volume-5 signals after RTH close,
enter at next session first 15m open. Fixed +3/-3 barriers or hold-to-close,
no new entry while an earlier position is open. Costs 15bps/side (30bps
roundtrip), EOD mark-to-market including entry-cost reserve and exit costs.
Per-ticker subaccounts: equal 20% INITIAL capital each, no sleeve rebalance.
This is a sensitivity experiment on ALREADY VIEWED historical years, not OOS.
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

from research.kalman_integrated_regime.us_multisymbol_volume_screen import (
    PRICE,VOLUME,build_daily_rows,matched_cohorts,
)
from research.kalman_integrated_regime.us_multisymbol_volume_trade_backtest import (
    session_paths,
)

SYMBOLS=("COIN","IWM","MU","SMH","SPY")
ARMS={"P_unweighted":PRICE,"V_unweighted":PRICE+VOLUME}
HORIZONS=(1,2,4)
EXIT_POLICIES=("RTH_FINAL_CLOSE","BARRIER_TP3_SL3")
SIDE_COST=.0015  # 10bps fee + 5bps assumed slippage per side
TP,SL=.03,.03
SIGNAL_THRESHOLD=.5


def one_session_path(path,entry,barrier=True):
    """Price/first crossing relative to original trade entry; stop wins ties.

    On a later session's open, a stop gap is filled at the WORSE opening
    price; take gap is conservatively filled at the specified limit.
    """
    if entry<=0 or path.empty:
        raise ValueError("INVALID_ENTRY_OR_PATH")
    if not barrier:
        return None,None
    stop,take=entry*(1-SL),entry*(1+TP)
    for bar in path.itertuples(index=False):
        op,hi,lo=float(bar.open),float(bar.high),float(bar.low)
        if op<=stop:
            return op,"STOP_GAP"
        if op>=take:
            return take,"TAKE_LIMIT"
        if lo<=stop and hi>=take:
            return stop,"STOP_FIRST_AMBIGUOUS"
        if lo<=stop:
            return stop,"STOP"
        if hi>=take:
            return take,"TAKE"
    return None,None


def daily_ledger(dates,flags,paths,ticker,horizon,exit_policy,side_cost=SIDE_COST):
    """EOD wealth trace; when holding, mark remaining exposure at daily close.

    Equity at close relative to entry is (mark/entry - side_cost) while still
    holding; at exit it is (fill/entry - 2*side_cost). Ratio versus previous
    marked wealth implements close-to-close daily PnL for overnight positions.
    Stop/TP checks use each session's full 15min OHLC, no future signal.
    """
    if horizon not in HORIZONS or exit_policy not in EXIT_POLICIES:
        raise ValueError("INVALID_POLICY_OR_HORIZON")
    dates=[pd.Timestamp(x) for x in dates]
    flags=np.asarray(flags,dtype=bool)
    if len(dates)!=len(flags) or not dates or dates!=sorted(set(dates)):
        raise ValueError("INVALID_PANEL_INDEX")
    if not 0<=side_cost<.1:
        raise ValueError("INVALID_SIDE_COST")
    if any((ticker,x) not in paths for x in dates):
        raise ValueError("MISSING_SESSION_PATH")
    # Identical candidate universe for all three horizons. Last 3 evaluation
    # dates only allow existing trades to close; never start a new trade.
    last_entry=len(dates)-max(HORIZONS)
    if last_entry<1:
        raise ValueError("NOT_ENOUGH_DATES_FOR_COMMON_ENTRY")
    cash_equity=1.
    equity_marks=[]
    position=None
    trade_details=[]
    blocked=0
    rejected_tail=0
    for idx,day in enumerate(dates):
        path=paths[(ticker,day)]
        if position is None and flags[idx]:
            if idx>last_entry:
                rejected_tail+=1
            else:
                op=float(path.iloc[0].open)
                if op<=0 or not np.isfinite(op):
                    raise ValueError("BAD_ENTRY_PRICE")
                position={"entry":op,"entry_index":idx,
                          "entry_date":str(day.date()),"prev_mark":1.}
        elif position is not None and flags[idx]:
            blocked+=1

        if position is not None:
            entry=position["entry"]
            elapsed=idx-position["entry_index"]+1
            hit_price,reason=one_session_path(
                path,entry,barrier=exit_policy=="BARRIER_TP3_SL3")
            should_exit=hit_price is not None or elapsed==horizon
            if should_exit:
                fill=float(hit_price if hit_price is not None else path.iloc[-1].close)
                reason=reason or "TIME_CLOSE"
                factor=fill/entry-2*side_cost
                if factor<=0 or not np.isfinite(factor):
                    raise ValueError("INVALID_EXIT_VALUE")
                daily_gross_mark=factor/position["prev_mark"]
                cash_equity*=daily_gross_mark
                trade_details.append({
                    "entry_date":position["entry_date"],
                    "exit_date":str(day.date()),
                    "trading_sessions_held":elapsed,
                    "net_return":factor-1,
                    "exit_reason":reason,
                })
                position=None
            else:
                close=float(path.iloc[-1].close)
                factor=close/entry-side_cost
                if factor<=0 or not np.isfinite(factor):
                    raise ValueError("INVALID_EOD_MARK")
                cash_equity*=factor/position["prev_mark"]
                position["prev_mark"]=factor
        equity_marks.append(cash_equity)
    if position is not None:
        raise AssertionError("OPEN_POSITION_AT_YEAR_END")
    wealth=np.asarray(equity_marks,dtype=float)
    peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
    md=float(np.min(wealth/peak-1))
    values=np.asarray([t["net_return"] for t in trade_details],dtype=float)
    return {
        "trades":len(trade_details),
        "blocked_signals_while_holding":blocked,
        "untradable_end_window_signals":rejected_tail,
        "trades_held_2plus_sessions":sum(t["trading_sessions_held"]>=2 for t in trade_details),
        "win_rate":round(float(np.mean(values>0)),7) if len(values) else None,
        "avg_trade_net_pct":round(float(np.mean(values)*100),7) if len(values) else None,
        "cumulative_return_pct":round(float((wealth[-1]-1)*100),6),
        "mdd_marked_eod_pct":round(float(md*100),6),
        "exit_reasons":{k:sum(t["exit_reason"]==k for t in trade_details)
                        for k in sorted({t["exit_reason"] for t in trade_details})},
        "_wealth":wealth,
        "_trades":trade_details,
    }


def make_signal_panels(bars):
    daily,quality=build_daily_rows(bars)
    paths=session_paths(bars)
    result={}
    for ticker,df in daily.groupby("symbol"):
        if ticker not in SYMBOLS:
            raise ValueError("UNAPPROVED_SYMBOL")
        for year in (2025,2026):
            train,test=matched_cohorts(df,year)
            test=test.loc[test.date_ny.dt.month.le(10)
                          &test.next_session_date.dt.month.le(10)].copy()
            if len(test)!=208:
                raise ValueError(f"UNEXPECTED_MATCHED_SAMPLE:{ticker}:{year}:{len(test)}")
            outcome=(train.next_session_rth_return.astype(float).to_numpy()>0).astype(int)
            if train.next_session_date.max()>=pd.Timestamp(f"{year}-01-01"):
                raise AssertionError("TRAIN_EXIT_LEAK")
            if len(np.unique(outcome))<2:
                raise ValueError("SINGLE_TRAIN_CLASS")
            signals={}
            for arm,columns in ARMS.items():
                model=make_pipeline(StandardScaler(),
                    LogisticRegression(class_weight=None,C=1.,
                                       random_state=42,max_iter=1000))
                model.fit(train[columns],outcome)
                signals[arm]=model.predict_proba(test[columns])[:,1]>=SIGNAL_THRESHOLD
            result[(ticker,year)]={"dates":list(test.next_session_date),
                                   "signals":signals}
    if set(result)!={(ticker,year) for ticker in SYMBOLS for year in (2025,2026)}:
        raise ValueError("UNIVERSE_YEAR_INCOMPLETE")
    for year in (2025,2026):
        reference=result[(SYMBOLS[0],year)]["dates"]
        if any(result[(ticker,year)]["dates"]!=reference for ticker in SYMBOLS):
            raise ValueError("MISMATCHED_TRADE_DATES")
    return result,paths,quality


def summarize(bars):
    panels,paths,quality=make_signal_panels(bars)
    ticker_results={}
    portfolios={}
    for year in (2025,2026):
        trackers={}
        for ticker in SYMBOLS:
            panel=panels[(ticker,year)]
            ticker_output={}
            for arm in ARMS:
                k={}
                for horizon in HORIZONS:
                    exits={}
                    for policy in EXIT_POLICIES:
                        ledger=daily_ledger(panel["dates"],panel["signals"][arm],
                                            paths,ticker,horizon,policy)
                        trackers[(ticker,arm,horizon,policy)]=ledger["_wealth"]
                        exits[policy]={key:value for key,value in ledger.items()
                                       if not key.startswith("_")}
                    k[str(horizon)]=exits
                ticker_output[arm]=k
            ticker_results.setdefault(ticker,{})[str(year)]=ticker_output
        for horizon in HORIZONS:
            for policy in EXIT_POLICIES:
                for arm in ARMS:
                    # 20% INITIAL capital to each sleeve, with NO daily
                    # inter-sleeve transfers, so each sleeve can hold 4 days.
                    marks=np.stack(
                        [trackers[(ticker,arm,horizon,policy)] for ticker in SYMBOLS])
                    wealth=marks.mean(axis=0)
                    peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
                    portfolios.setdefault(str(year),{}).setdefault(str(horizon),{}).setdefault(
                        policy,{})[arm]={
                        "return_pct":round(float((wealth[-1]-1)*100),6),
                        "mdd_eod_pct":round(float((wealth/peak-1).min()*100),6),
                        "total_transactions":sum(
                            ticker_results[ticker][str(year)][arm][str(horizon)][policy]["trades"]
                            for ticker in SYMBOLS),
                        "no_inter_sleeve_rebalance":True,
                    }
    return {
        "schema":"kalman-us-five-hold1-2-4-nonoverlap-barrier-v1",
        "status":"EXPLORATORY_RESEARCH_LIVE_HOLD",
        "source":"Alpaca SIP 15m adjustment=all; complete regular hours",
        "tickers":list(SYMBOLS),
        "horizons_trading_sessions":list(HORIZONS),
        "exit_policies":list(EXIT_POLICIES),
        "roundtrip_friction_bps":2*SIDE_COST*10000,
        "common_candidate_entry_dates_exclude_last_3_days":True,
        "blocked_overlapping_signal":True,
        "portfolio":"equal 20% of INITIAL capital in five independent sleeve accounts, no cross-sleeve rebalancing",
        "historical_source_quality":quality,
        "by_ticker":ticker_results,
        "portfolio":portfolios,
        "caveats":[
            "All 2025 and 2026 years were examined in prior research. NO independent OOS.",
            "Positions held overnight and exposed to overnight gaps unlike prior day-trade strategy.",
            "First intraday bar OPEN entry assumes an idealized next-open fill; actual spread and slippage are not observed.",
            "Intraday 15m OHLC crossing ambiguous; stop-first conservative, stop-gap open may understate loss beyond barrier.",
            "Roundtrip total friction fixed at 30bps, not measured realized commissions or market impacts.",
            "Daily close MDD marks positions at closing 15min price and books entry fees before close and exit costs on exit.",
            "One trade per ticker at a time: new signals during open position are ignored, not queued.",
            "Same entry-eligible dates across 1/2/4 session horizons; last three sample dates have no new entries.",
            "Equal-initial-weight sleeves compound independently and do not rebalance; not the same as daily 20% weights.",
            "No dividends, margin, short sales, taxes or uncertainty intervals are modeled.",
        ],
        "live_changes":False,
        "promotion":"HOLD",
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-bars",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    result=summarize(pd.read_parquet(args.input_bars))
    path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("HOLD1_2_4_NONOVERLAP "+json.dumps({
        "status":result["status"],
        "COIN":result["by_ticker"]["COIN"],
        "portfolio":result["portfolio"],
        "promotion":result["promotion"]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
