#!/usr/bin/env python3
"""Kalman research: causal market regime and realized trade reward/risk audit.

Regimes use only SPY observations available by completed signal-day RTH close:
50-session SMA, its prior-ten-session slope, and trailing 20-session return.
Separate market-volatility and ticker-relative-volume axes are also derived
from data available by the signal close. NO trade P&L enters regime labels.
Outcomes are evaluated later, for trades actually entered under each regime.

Research-only; historical 2025-2026 is repeatedly consulted, not pristine OOS.
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
from research.kalman_integrated_regime.us_multisymbol_volume_trade_backtest import session_paths
from research.kalman_integrated_regime.us_multisymbol_hold124 import (
    SYMBOLS, HORIZONS, SIDE_COST, TP, SL, daily_ledger,
)

ARMS = {"P_unweighted": PRICE, "V_unweighted": PRICE + VOLUME}
POLICY = "BARRIER_TP3_SL3"
MIN_DESCRIPTIVE_TRADES = 15


def ex_ante_reward_risk(tp=TP, sl=SL, side_cost=SIDE_COST):
    """Potential net TP divided by planned net stop loss, before gap risk.

    This is an illustrative planned gross-barrier ratio, not the realized
    payoff ratio. For forced time exits or stop gaps, realized R differs.
    """
    if not (0 < tp < 1 and 0 < sl < 1 and 0 <= side_cost < .05):
        raise ValueError("BAD_RISK_POLICY")
    roundtrip = 2 * side_cost
    reward = tp - roundtrip
    risk = sl + roundtrip
    if reward <= 0:
        raise ValueError("COST_EXCEEDS_PLANNED_REWARD")
    return {
        "tp_fraction": round(tp, 7),
        "sl_fraction": round(sl, 7),
        "assumed_roundtrip_cost_fraction": round(roundtrip, 7),
        "planned_win_net_fraction": round(reward, 7),
        "planned_stop_loss_net_fraction": round(risk, 7),
        "planned_reward_to_risk": round(reward / risk, 7),
        "simple_barrier_breakeven_win_fraction": round(risk / (reward + risk), 7),
        "realized_gaps_and_time_exits_may_change_break_even": True,
    }


def spy_market_states(spy):
    """Point-in-time regimes based on a completed SPY RTH daily close.

    Labels:
     BULL: close > 50-session mean, MA50 slope 10d > 0, return20 > 0.
     BEAR: symmetric three strictly negative predicates.
     TRANSITION: remaining complete observations.
     UNAVAILABLE: insufficient history or incomplete daily bars.

    High-vol flag uses trailing realized vol20 vs prior 60-session median;
    its threshold is not fitted on any test-year trading return.
    """
    d = spy.sort_values("date_ny").copy()
    if not d.date_ny.is_unique:
        raise ValueError("DUPLICATE_SPY_SESSION")
    c = d.rth_close.astype(float).where(d.complete_rth)
    ma50 = c.rolling(50, min_periods=50).mean()
    slope10 = ma50 / ma50.shift(10) - 1
    r20 = c / c.shift(20) - 1
    valid = d.complete_rth & ma50.notna() & slope10.notna() & r20.notna()
    bull = valid & c.gt(ma50) & slope10.gt(0) & r20.gt(0)
    bear = valid & c.lt(ma50) & slope10.lt(0) & r20.lt(0)
    state = np.select([bull, bear, valid],
                      ["BULL", "BEAR", "TRANSITION"], default="UNAVAILABLE")
    vol20 = np.log(c/c.shift(1)).rolling(20, min_periods=20).std()
    vol_baseline = vol20.shift(1).rolling(60, min_periods=60).median()
    high_vol = vol20.gt(vol_baseline)
    vol_available = vol20.notna() & vol_baseline.notna()
    return pd.DataFrame({
        "date_ny": d.date_ny.to_numpy(),
        "market_state": state,
        "market_volatility_state": np.where(
            vol_available, np.where(high_vol, "HIGH", "LOW"), "UNAVAILABLE"
        )
    })


def trade_group_stats(trades, planned_risk_fraction, min_trades=MIN_DESCRIPTIVE_TRADES):
    """Compounds selected actually executed trade outcomes, not daily equity.

    Mean R and win rate are descriptive, not a claim of significance.
    Each trade's R denominator is the pre-entry +3% gross stop plus costs;
    gap and end-of-horizon exits use the actual simulated net return.
    """
    if planned_risk_fraction <= 0:
        raise ValueError("NONPOSITIVE_RISK_DENOMINATOR")
    if not trades:
        return {"count": 0, "status": "NO_TRADES", "expectancy_R": None,
                "compounded_executed_trades_return_pct": None}
    values = np.array([float(x["net_return"]) for x in trades])
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("INVALID_TRADE_RETURN")
    winners = values[values > 0]
    losers = values[values < 0]
    in_r = values / planned_risk_fraction
    by_reason = {}
    for t in trades:
        why = t.get("exit_reason", "UNKNOWN")
        by_reason[why] = by_reason.get(why, 0) + 1
    payoff = (float(winners.mean()) / abs(float(losers.mean()))
              if len(winners) and len(losers) else None)
    return {
        "count": len(trades),
        "status": "DESCRIPTIVE_ONLY" if len(trades) >= min_trades else "INSUFFICIENT_SAMPLE",
        "win_rate": round(float(len(winners) / len(trades)), 7),
        "mean_winner_net_pct": round(float(100*winners.mean()), 6) if len(winners) else None,
        "mean_loser_net_pct": round(float(100*losers.mean()), 6) if len(losers) else None,
        "realized_win_to_loss_payoff_ratio": round(payoff, 7) if payoff is not None else None,
        "expectancy_R": round(float(in_r.mean()), 7),
        "median_realized_R": round(float(np.median(in_r)), 7),
        "worst_realized_R": round(float(in_r.min()), 7),
        "compounded_executed_trades_return_pct":
            round(float((np.prod(1 + values)-1)*100), 6),
        "mean_holding_sessions": round(
            float(np.mean([x["trading_sessions_held"] for x in trades])), 5),
        "exit_reasons": by_reason,
        "trade_chain_is_not_calendar_portfolio_return": True,
    }


def audited_cohort(trades, candidate_dates, signal_meta, risk_fraction):
    """Group executed entries under the regime recorded BEFORE entry."""
    by_date = {pd.Timestamp(x["trade_date"]): x for x in signal_meta}
    if len(by_date) != len(signal_meta):
        raise AssertionError("DUPLICATE_META_TRADE_DATE")
    classified = []
    for t in trades:
        key = pd.Timestamp(t["entry_date"])
        if key not in by_date:
            raise ValueError("ENTRY_HAS_NO_PRETRADE_REGIME")
        meta = by_date[key]
        if meta["market_state"] == "UNAVAILABLE":
            raise ValueError("ENTERED_WITHOUT_MARKET_STATE")
        classified.append((t, meta))
    output = {}
    for axis, values in {
        "market_state": ("BULL", "BEAR", "TRANSITION"),
        "market_volatility_state": ("HIGH", "LOW"),
        "ticker_volume_state": ("RVOL_GE_2", "RVOL_LT_2"),
    }.items():
        output[axis] = {}
        for state in values:
            subset = [t for t, meta in classified if meta[axis] == state]
            eligible = sum(1 for meta in signal_meta if meta[axis] == state)
            output[axis][state] = {
                "candidate_signal_days": eligible,
                **trade_group_stats(subset, risk_fraction),
            }
        if sum(x["count"] for x in output[axis].values()) != len(trades):
            raise AssertionError("REGIME_CLASSIFICATION_DROPPED_EXECUTED_TRADE")
    return {
        "total_executed": len(trades),
        "by_axis": output,
        "conditional_trade_return_basis": "entry-date Regime, executed long trades only",
    }


def run(bars):
    daily, qa = build_daily_rows(bars)
    paths = session_paths(bars)
    if set(daily.symbol.unique()) != set(SYMBOLS):
        raise ValueError("UNIVERSE_NOT_FIVE_TICKERS")
    market = spy_market_states(daily.loc[daily.symbol.eq("SPY")])
    market_map = {
        pd.Timestamp(row.date_ny): {
            "market_state": row.market_state,
            "market_volatility_state": row.market_volatility_state,
        }
        for row in market.itertuples(index=False)
    }
    rr = ex_ante_reward_risk()
    result = {}
    for ticker, records in daily.groupby("symbol", sort=True):
        by_year = {}
        for year in (2025, 2026):
            train, test = matched_cohorts(records, year)
            test = test.loc[
                test.date_ny.dt.month.le(10)
                & test.next_session_date.dt.month.le(10)
            ].copy()
            if len(test) != 208:
                raise ValueError(f"UNEXPECTED_TEST_DAYS:{ticker}:{year}:{len(test)}")
            y = (train.next_session_rth_return.astype(float).to_numpy() > 0).astype(int)
            if len(np.unique(y)) != 2:
                raise ValueError("ONE_TRAIN_CLASS")
            dates = [pd.Timestamp(x) for x in test.next_session_date]
            signal_meta = []
            for row in test.itertuples(index=False):
                snapshot = market_map.get(pd.Timestamp(row.date_ny))
                if snapshot is None or snapshot["market_state"] == "UNAVAILABLE":
                    raise ValueError("MARKET_REGIME_NOT_AVAILABLE_BY_SIGNAL_CLOSE")
                if snapshot["market_volatility_state"] == "UNAVAILABLE":
                    raise ValueError("MARKET_VOLATILITY_HISTORY_NOT_AVAILABLE")
                signal_meta.append({
                    "trade_date": pd.Timestamp(row.next_session_date),
                    **snapshot,
                    "ticker_volume_state": "RVOL_GE_2" if row.rvol20 >= 2 else "RVOL_LT_2"
                })
            decisions = {}
            for arm, cols in ARMS.items():
                model = make_pipeline(
                    StandardScaler(),
                    LogisticRegression(C=1., max_iter=1000,
                                       class_weight=None, random_state=42)
                )
                model.fit(train[cols], y)
                decisions[arm] = model.predict_proba(test[cols])[:, 1] >= .5
            arms = {}
            for arm, flags in decisions.items():
                horizons = {}
                for h in HORIZONS:
                    ledger = daily_ledger(dates, flags, paths, ticker, h, POLICY)
                    by_regime = audited_cohort(
                        ledger["_trades"], dates, signal_meta,
                        rr["planned_stop_loss_net_fraction"]
                    )
                    if by_regime["total_executed"] != ledger["trades"]:
                        raise AssertionError("TRADE_GROUP_COUNT_MISMATCH")
                    horizons[str(h)] = {
                        "trades": ledger["trades"],
                        "cumulative_return_pct": ledger["cumulative_return_pct"],
                        "mdd_marked_eod_pct": ledger["mdd_marked_eod_pct"],
                        "blocked_signals": ledger["blocked_signals_while_holding"],
                        "regime": by_regime,
                    }
                arms[arm] = horizons
            by_year[str(year)] = {
                "matched_test_days": len(test),
                "market_regime_is_labelled_on_prior_completed_signal_day": True,
                "arms": arms,
            }
        result[ticker] = by_year
    return {
        "schema": "kalman-us-five-market-regime-planned-rr-realized-r-v1",
        "status": "RESEARCH_ONLY_NOT_LIVE_VALIDATED",
        "tickers": list(SYMBOLS),
        "market_proxy": "SPY trailing completed RTH close (not trade outcome)",
        "market_label_rule": {
            "BULL": "SPY close above 50D SMA; 50D SMA 10D slope positive; 20D return positive",
            "BEAR": "SPY close below 50D SMA; 50D SMA 10D slope negative; 20D return negative",
            "TRANSITION": "other valid current closes",
            "regime_assigned": "T RTH close, trade opens T+1",
        },
        "separate_axes": [
            "market trend state",
            "SPY realized volatility20 high/low vs previous60-day median",
            "ticker full-session RVOL20 >= 2 versus below 2",
        ],
        "planned_trade_rr": rr,
        "entry_arms": {k: v for k, v in ARMS.items()},
        "horizons_sessions": list(HORIZONS),
        "exit": "intraday ±3% touch, conservative stop-first; otherwise end of horizon close",
        "by_ticker": result,
        "source_quality": qa,
        "promotion": "HOLD",
        "caveats": [
            "Historical 2025 and 2026 were repeatedly examined, so this is descriptive, NOT untouched out-of-sample validation.",
            "Regimes are fixed, interpretable provisional labels, not a trained HMM or validated causal state estimator.",
            "Bull market experience is a hypothesis; do not infer regime edge without comparing risk, exposure, sample size and unseen data.",
            "No trading return is used to construct labels; only SPY history available at the prior signal close.",
            "Planned reward:risk of 0.818 assumes ±3% gross barriers and a 0.30% roundtrip cost; gaps and forced time exits can invalidate planned payoff.",
            "Regime compound return chains trade outcomes in each entry state and IS NOT a contemporaneous daily portfolio-equity curve.",
            "Symbols may be highly correlated; shared market days are not independent samples.",
            "15m OHLC cannot identify first touch within one bar; stop-first rule applies.",
            "All five tickers have their own independent capital sleeves; LIVE is not modified.",
        ],
        "live_changed": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-bars", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = run(pd.read_parquet(args.input_bars))
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    compact = {
        symbol: {
            year: {
                arm: {
                    horizon: {
                        "overall_return_pct": data["cumulative_return_pct"],
                        "overall_mdd_pct": data["mdd_marked_eod_pct"],
                        "market": {
                            key: {
                                "n": value["count"],
                                "net_R": value["expectancy_R"],
                                "trade_chain_return_pct": value["compounded_executed_trades_return_pct"],
                            }
                            for key, value in data["regime"]["by_axis"]["market_state"].items()
                        }
                    }
                    for horizon, data in horizons.items()
                }
                for arm, horizons in yr["arms"].items()
            }
            for year, yr in years.items()
        }
        for symbol, years in report["by_ticker"].items()
    }
    print("KALMAN_REGIME_RR_SUMMARY " + json.dumps(compact, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
