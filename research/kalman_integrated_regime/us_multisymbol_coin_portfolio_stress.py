#!/usr/bin/env python3
"""Research-only 5 ticker cost stress, COIN year/regime attribution and portfolio.

Uses the ALREADY SPECIFIED, NO-OVERLAP, one-session Kalman research policy:
signal at completed T RTH close, enter NEXT RTH open, exit next RTH close
or intraday TP+3%/SL-3%. Price-3 vs price+RVOL/zscore-5, fit ONLY before
test year, on IDENTICAL Jan-Oct test dates. Do not use this for orders.

Assumed observed opening-bar fill and fixed per-roundtrip costs are idealized.
No policy selection, live changes or genuine untouched OOS claim.
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
    PRICE, VOLUME, build_daily_rows, matched_cohorts,
)
from research.kalman_integrated_regime.us_multisymbol_volume_trade_backtest import (
    session_paths, intraday_exit,
)

SYMBOLS=("COIN","IWM","MU","SMH","SPY")
ARMS={"P_unweighted":PRICE, "V_unweighted":PRICE+VOLUME,
      "ALWAYS_INTRADAY_LONG":None}
POLICIES=("NEXT_RTH_CLOSE","SAME_SESSION_TP3_SL3")
COST_BPS=(0,10,30,50,100)
FIXED_COST_BPS=30
ENTRY_PROBABILITY=.5
REALLOCATION="equal 20% of current total capital to each of five sleeves EVERY session"


def round_f(v):
    return round(float(v),6)


def metrics(daily_returns,trade_mask):
    ret=np.asarray(daily_returns,dtype=float)
    mask=np.asarray(trade_mask,dtype=bool)
    if len(ret)==0 or len(ret)!=len(mask) or not np.isfinite(ret).all() or (ret<=-1).any():
        raise ValueError("INVALID_RETURN_TRACE")
    eq=np.cumprod(1+ret)
    peaks=np.maximum.accumulate(np.r_[1.0,eq])[1:]
    drawdowns=eq/peaks-1.0
    wins=int(((ret>0)&mask).sum())
    return {
        "days":int(len(ret)),
        "trades":int(mask.sum()),
        "cumulative_return_pct":round_f((eq[-1]-1)*100),
        "mdd_daily_close_pct":round_f(drawdowns.min()*100),
        "avg_exposure_fraction":round_f(mask.mean()),
        "win_rate_per_trade":round_f(wins/mask.sum()) if mask.any() else None,
        "mean_trade_net_pct":round_f(ret[mask].mean()*100) if mask.any() else None,
    }


def net_returns(gross,signal,cost_bps):
    """Long-flat payoff; explicit fixed total roundtrip fee+slippage in bps."""
    gross=np.asarray(gross,dtype=float)
    signal=np.asarray(signal,dtype=bool)
    if len(gross)!=len(signal) or cost_bps<0 or cost_bps>300:
        raise ValueError("COST_OR_SIGNAL_INVALID")
    out=np.where(signal,gross-cost_bps/10000.,0.)
    if (out<=-1).any():
        raise ValueError("NONPOSITIVE_EQUITY_STEP")
    return out


def make_panel(bars):
    """An in-memory per-symbol daily data panel; output only summaries."""
    df,quality=build_daily_rows(bars)
    paths=session_paths(bars)
    panels={}
    for ticker,frame in df.groupby("symbol",sort=True):
        if ticker not in SYMBOLS:
            raise ValueError("UNEXPECTED_TICKER")
        for year in (2025,2026):
            train,test=matched_cohorts(frame,year)
            test=test.loc[test.date_ny.dt.month.le(10)
                          & test.next_session_date.dt.month.le(10)].copy()
            if len(test)<180:
                raise ValueError(f"TOO_FEW_SIGNAL_DATES:{ticker}:{year}")
            if train.next_session_date.max()>=pd.Timestamp(f"{year}-01-01"):
                raise AssertionError("FUTURE_LABEL_IN_TRAINING")
            y=(train.next_session_rth_return.astype(float).to_numpy()>0).astype(int)
            if len(np.unique(y))!=2:
                raise ValueError("TRAIN_LABEL_ONE_CLASS")
            p=test.copy()
            p["signal_date"]=pd.to_datetime(test.date_ny)
            p["trade_date"]=pd.to_datetime(test.next_session_date)
            if not p.trade_date.is_unique or not p.trade_date.is_monotonic_increasing:
                raise AssertionError("NONUNIQUE_OR_UNSORTED_TRADE_DAYS")
            high_vol_cutoff=float(train.price_logvol20.quantile(.67))
            if not np.isfinite(high_vol_cutoff):
                raise ValueError("TRAIN_VOLATILITY_CUTOFF_INVALID")
            p["regime_train_high_price_vol"]=test.price_logvol20>=high_vol_cutoff
            p["regime_prior20_negative"]=test.price_r20<0
            p["regime_rvol2"]=test.rvol20>=2
            for name,cols in ARMS.items():
                if cols is None:
                    p["signal_"+name]=True
                else:
                    model=make_pipeline(StandardScaler(),
                                        LogisticRegression(C=1.,class_weight=None,
                                                           random_state=42,max_iter=1000))
                    model.fit(train[cols],y)
                    probabilities=model.predict_proba(test[cols])[:,1]
                    p["signal_"+name]=probabilities>=ENTRY_PROBABILITY
            for policy in POLICIES:
                outcomes=[intraday_exit(paths[(ticker,pd.Timestamp(day))],policy)[0]
                          for day in p.trade_date]
                if not np.isfinite(outcomes).all():
                    raise ValueError("NONFINITE_GROSS")
                p["gross_"+policy]=outcomes
            panels[(ticker,year)]=p
    if set(panels)!={(ticker,year) for ticker in SYMBOLS for year in (2025,2026)}:
        raise AssertionError("FIVE_TICKER_TWO_YEAR_COVERAGE_NOT_COMPLETE")
    for year in (2025,2026):
        first=list(panels[(SYMBOLS[0],year)].trade_date)
        for sym in SYMBOLS[1:]:
            if list(panels[(sym,year)].trade_date)!=first:
                raise AssertionError("NOT_SAME_SESSION_PANEL:"+str(year)+":"+sym)
    return panels,quality


def monthly_attribution(panel,policy,arm,cost_bps=FIXED_COST_BPS):
    signal=panel["signal_"+arm].to_numpy(dtype=bool)
    net=net_returns(panel["gross_"+policy],signal,cost_bps)
    f=pd.DataFrame({"trade_date":panel.trade_date.values,"net":net,"signal":signal,
                    "rvol2":panel.regime_rvol2.values,
                    "high_vol":panel.regime_train_high_price_vol.values,
                    "negative_trend":panel.regime_prior20_negative.values})
    f["month"]=pd.to_datetime(f.trade_date).dt.strftime("%Y-%m")
    grouped=[]
    for month,g in f.groupby("month",sort=True):
        grp=g.loc[g.signal]
        grouped.append({
            "month":month,
            "trades":int(g.signal.sum()),
            "net_compounded_return_pct":round_f(100*(np.prod(1+g.net)-1)),
            "positive_trade_count":int((grp.net>0).sum()),
            "net_log_return_contribution_pct":round_f(100*np.log1p(g.net).sum()),
            "rvol2_signal_count":int((grp.rvol2).sum()),
            "high_train_vol_signal_count":int((grp.high_vol).sum()),
            "prior20_negative_signal_count":int((grp.negative_trend).sum()),
        })
    return grouped,net,signal


def concentration(panel,policy,arm,cost_bps=FIXED_COST_BPS):
    months,net,signal=monthly_attribution(panel,policy,arm,cost_bps)
    log=np.log1p(net)
    traded_log=log[signal]
    positive=np.sort(traded_log[traded_log>0])[::-1]
    positive_total=float(positive.sum())
    def excluding_top(k):
        ranked=np.flatnonzero((net>0)&signal)
        top=ranked[np.argsort(net[ranked])[-k:]]
        copy=net.copy()
        copy[top]=0.
        return round_f(100*(np.prod(1+copy)-1))
    out={
        "first_half_months":"Jan-Jun",
        "second_half_months":"Jul-Oct",
        "monthly":months,
        "positive_months":sum(m["net_compounded_return_pct"]>0 for m in months),
        "gross_positive_trade_log_contribution_pct_from_top_5":
            round_f(100*positive[:5].sum()/positive_total) if positive_total>0 else None,
        "return_if_top_1_positive_trade_day_removed_pct":excluding_top(1),
        "return_if_top_3_positive_trade_days_removed_pct":excluding_top(3),
        "return_if_top_5_positive_trade_days_removed_pct":excluding_top(5),
        "removed_top_days_are_diagnostic_not_investable":True,
    }
    for region,mask in (("Jan-Jun",panel.trade_date.dt.month.le(6)),
                        ("Jul-Oct",panel.trade_date.dt.month.ge(7))):
        i=np.asarray(mask,dtype=bool)
        out[region]=metrics(net[i],signal[i]) if i.any() else {"days":0,"trades":0,"status":"NO_OBSERVATIONS"}
    for regime,flag in (
        ("signal_day_prior20_price_decline",panel.regime_prior20_negative),
        ("signal_day_prior20_price_nonnegative",~panel.regime_prior20_negative),
        ("signal_day_rvol_ge2",panel.regime_rvol2),
        ("signal_day_train67_price_vol_high",panel.regime_train_high_price_vol),
    ):
        i=np.asarray(flag,dtype=bool)
        out[regime]={
            "observed_signal_days":int(i.sum()),
            "trades":int((signal&i).sum()),
            "net_log_growth_contribution_pct":round_f(100*log[i].sum()),
            "positive_trade_fraction":round_f(((net>0)&signal&i).sum()/(signal&i).sum())
                if (signal&i).any() else None,
        }
    return out


def summarize_panels(panels,quality):
    by_symbol={}
    portfolios={}
    coin_diagnostics={}
    for ticker in SYMBOLS:
        by_year={}
        for year in (2025,2026):
            p=panels[(ticker,year)]
            by_policy={}
            for policy in POLICIES:
                gross=p["gross_"+policy].to_numpy(dtype=float)
                arm_results={}
                for arm in ARMS:
                    flag=p["signal_"+arm].to_numpy(dtype=bool)
                    scores={}
                    for cost in COST_BPS:
                        net=net_returns(gross,flag,cost)
                        scores[str(cost)]=metrics(net,flag)
                    arm_results[arm]=scores
                by_policy[policy]={"cost_sensitivity_roundtrip_bps":arm_results,
                    "v_minus_p_return_pp_at_30bps":round_f(
                        arm_results["V_unweighted"]["30"]["cumulative_return_pct"]-
                        arm_results["P_unweighted"]["30"]["cumulative_return_pct"])}
            by_year[str(year)]={
                "n_common_days":len(p),"policies":by_policy,
                "train_cutoffs_fitted_before_year":True}
            if ticker=="COIN":
                coin_diagnostics[str(year)]={
                    pol:concentration(p,pol,"V_unweighted")
                    for pol in POLICIES}
        by_symbol[ticker]=by_year
    for year in (2025,2026):
        year_result={}
        for policy in POLICIES:
            by_arm={}
            for arm in ARMS:
                by_cost={}
                for cost in COST_BPS:
                    arr=[]
                    exposures=[]
                    for ticker in SYMBOLS:
                        p=panels[(ticker,year)]
                        gross=p["gross_"+policy].to_numpy(dtype=float)
                        flag=p["signal_"+arm].to_numpy(dtype=bool)
                        arr.append(net_returns(gross,flag,cost))
                        exposures.append(flag)
                    daily=np.stack(arr,axis=0).mean(axis=0)
                    marks=np.stack(exposures,axis=0)
                    # 20% of total equity each ticker daily; nontraded sleeves cash.
                    report=metrics(daily,np.any(marks,axis=0))
                    report.update({
                        "total_ticker_trades":int(marks.sum()),
                        "max_simultaneous_positions":int(marks.sum(axis=0).max()),
                        "mean_simultaneous_positions":round_f(marks.sum(axis=0).mean()),
                        "mean_invested_portfolio_fraction":round_f(marks.mean()),
                        "capital_rebalanced_at_each_session_open":True,
                    })
                    by_cost[str(cost)]=report
                by_arm[arm]=by_cost
            year_result[policy]=by_arm
        portfolios[str(year)]=year_result
    return {
        "schema":"kalman-us-five-coin-concentration-cost-stress-equalweight-v1",
        "status":"EXPLORATORY_COST_STRESS_LIVE_HOLD",
        "periods":"2025 and 2026 Jan-Oct (signal AND next-session trade)",
        "universe":list(SYMBOLS),
        "models":{arm:cols for arm,cols in ARMS.items()},
        "cost_grid_roundtrip_bps":list(COST_BPS),
        "fixed_cost_reconciliation_roundtrip_bps":FIXED_COST_BPS,
        "policies":list(POLICIES),
        "portfolio":REALLOCATION,
        "universe_source_qa":quality,
        "by_symbol":by_symbol,
        "equalweight_daily_rebalance_portfolio":portfolios,
        "coin_concentration":coin_diagnostics,
        "caveats":[
            "Not genuine untouched OOS: user and assistant have repeatedly inspected 2025/2026 and COIN 2026 result.",
            "Per-symbol training cutoffs and fitted logistic models use prior years only, but post-hoc feature/policy research is adaptive.",
            "Portfolio assumes exact fractional 20% sleeve rebalancing each day, 100% of sleeve for all signaled symbols, 0 on remaining. No portfolio margin.",
            "All ticker signals share dates; portfolio return = equal weighted average of five net daily sleeve returns, compounded once daily.",
            "Transaction costs are hypothetical fixed total roundtrip basis points, not realized spread, actual slip, partial fills or market impact.",
            "Historical next-open fills assumed at adjusted bar open; stop-first within ambiguous 15-min OHLC only.",
            "MDD is daily-close equity MDD, never intraday and not risk-adjusted for portfolio tail correlations.",
            "Removing top winning days or slicing regimes is retrospective diagnostic; never use it to select a live regime from the test data.",
            "No 2–4 session holding or reinvestment overnight in this contract; do not compare as QLD 4-session strategy.",
            "Any raw licensed source tape remains temporary; publish only derived monthly aggregates and performance.",
        ],
        "live_changed":False,
        "promotion":"HOLD",
    }


def run(bars):
    panels,quality=make_panel(bars)
    return summarize_panels(panels,quality)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-bars",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    result=run(pd.read_parquet(args.input_bars))
    dest=Path(args.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    compact={
        "status":result["status"],
        "coin":{year:{policy:{
            "at_30bps":result["by_symbol"]["COIN"][year]["policies"][policy]
                ["cost_sensitivity_roundtrip_bps"]["V_unweighted"]["30"],
            "monthly":data["monthly"],
            "removed_top5_pct":data["return_if_top_5_positive_trade_days_removed_pct"],
        } for policy,data in records.items()}
        for year,records in result["coin_concentration"].items()},
        "portfolio":{year:{policy:{arm:costs["30"]
                   for arm,costs in arms.items()}
                   for policy,arms in yr.items()}
                   for year,yr in result["equalweight_daily_rebalance_portfolio"].items()},
        "hold_live":True,
    }
    print("KALMAN_US_FIVE_COST_STRESS "+json.dumps(compact,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
