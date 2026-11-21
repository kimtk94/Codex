#!/usr/bin/env python3
"""Daily20 independent, OOS bear-regime challengers and equity-decay attribution.

Research ONLY. This never alters Kalman live, R5, or the existing bull-entry
signal generator. No hindsight regime labels, no test-year threshold tuning,
and no model promotion based on 2024–2026 performance.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from daily20 import load_spec, write_json
from train import (COLUMNS, context_frame, feature_frame, model, model_split,
                   nonoverlap)
from portfolio import (INITIAL_CASH, buy_hold, classify_state,
                       conditional_daily_stats, market_state, performance,
                       prepared_events, prices_from_market, simulate,
                       trade_group_stats, validate_sessions)

VERSION = "daily20-bear-oos-v1"
BEAR_VIX_MAX = 45.0
BEAR_RSI_LOW = 30.0
BEAR_RSI_HIGH = 60.0
MIN_BEAR_TRAIN = 126
ML_THRESHOLD = 0.60
COSTS = (20.0, 40.0)
EQUITY_FRACTION = .20
CAPACITY = 5
COHORTS = ("ALL_20", "EXCLUDE_HIGH_RISK")
SCENARIOS = (
    "BULL_BASELINE",
    "BEAR_RULE_ONLY",
    "BEAR_LOGISTIC_ONLY",
    "BULL_PLUS_BEAR_RULE",
    "BULL_PLUS_BEAR_LOGISTIC",
)
TRADES_SCHEMA = (
    "symbol", "strategy", "signal_date", "entry_date", "exit_date",
    "gross_return", "net_return", "probability", "regime", "candidate_family"
)


def bear_gate(df):
    """All features known on signal-date close; market context lagged 1 session."""
    return (df["spy_above200_lag"].lt(.5)
            & df["spy_above200_lag"].notna()
            & df["vix_lag"].gt(0)
            & df["vix_lag"].le(BEAR_VIX_MAX))


def rule_gate(df):
    """Frozen ex-ante mean-reversion hypothesis; NOT selected from OOS years.

    The prior bear regime avoids fitting a bear designation to today's drop.
    RSI, MACD and 1d close return are all known after today's daily bar closes.
    """
    return (bear_gate(df)
            & df["rsi14"].between(BEAR_RSI_LOW, BEAR_RSI_HIGH)
            & df["ret1"].gt(0.0)
            & df["macd_hist"].gt(df["macd_hist"].shift(1)))


def fit_bear_year(frame, year):
    """Fit strictly on historical BEAR rows with label purge across year split."""
    train, test = model_split(frame, year)
    eligible_train = train[bear_gate(train)]
    year_report = {
        "year": year, "bear_training_rows": int(len(eligible_train)),
        "bear_test_sessions": int(bear_gate(test).sum()),
        "all_test_sessions": int(len(test)),
    }
    labels = (eligible_train["net_return"] > 0).astype(int)
    if len(test) < 10:
        return None, test, {**year_report, "status": "INSUFFICIENT_TEST_DATA"}
    if len(eligible_train) < MIN_BEAR_TRAIN or labels.nunique() < 2:
        return None, test, {**year_report, "status": "INSUFFICIENT_BEAR_TRAINING"}
    estimator = model()  # Same fixed Logistic hyperparameters as original research.
    estimator.fit(eligible_train[COLUMNS], labels)
    subset = test.copy()
    subset["prob"] = estimator.predict_proba(subset[COLUMNS])[:, 1]
    return estimator, subset, {**year_report, "status": "OOS_BEAR_MODEL_EVALUATED"}


def make_bear_candidates(spec, market, features):
    """Only historical completed OOS labels; recent unresolved trades are absent."""
    contexts = context_frame(market)
    rows = []
    folds = {}
    raw_coverage = []
    threshold = float(ML_THRESHOLD)
    for symbol in spec["core"]:
        frame = feature_frame(symbol, market, features, contexts,
                              spec["round_trip_cost_bps"])
        model_parts, rule_parts, symbol_folds = [], [], []
        endyear = int(frame.index.max().year)
        for year in range(int(spec["first_test_year"]), endyear + 1):
            fitted, test, fold = fit_bear_year(frame, year)
            symbol_folds.append(fold)
            eligible = bear_gate(test) & test["net_return"].notna()
            rule_allowed = rule_gate(test) & test["net_return"].notna()
            raw_coverage.append({
                "symbol": symbol, "year": year,
                "completed_label_rows": int(test["net_return"].notna().sum()),
                "bear_gate_rows": int(eligible.sum()),
                "rule_qualified_rows": int(rule_allowed.sum()),
                "logistic_qualified_rows": (
                    int((eligible & test["prob"].ge(threshold)).sum())
                    if fitted is not None else 0),
                "bear_model_fit": fitted is not None,
            })
            if fitted is not None:
                # A row's OOS probability was trained only on earlier years.
                model_parts.append(test[eligible & test["prob"].ge(threshold)])
            rule_parts.append(test[rule_allowed])
        folds[symbol] = symbol_folds
        for family, strategy, pieces in (
            ("BEAR_LOGISTIC", "LOGISTIC", model_parts),
            ("BEAR_RULE", "TREND_RULE", rule_parts),
        ):
            if not pieces:
                continue
            selected = nonoverlap(pd.concat(pieces), strategy)
            for trade in selected:
                if trade["regime"] != "BEAR":
                    raise RuntimeError("BEAR_ONLY_CHALLENGER_BREACHED")
                rows.append({"symbol": symbol, **trade, "candidate_family": family})
    out = pd.DataFrame(rows, columns=TRADES_SCHEMA)
    coverage = pd.DataFrame(raw_coverage)
    if len(coverage) != 20 * (endyear - spec["first_test_year"] + 1):
        raise RuntimeError("INCOMPLETE_20_SYMBOL_OOS_COVERAGE")
    return out, coverage, folds


def regime_days(state, sessions):
    """A market's condition at t uses only the prior completed session."""
    rows = []
    for dt in sessions:
        trend, volatility, tech = classify_state(state.loc[dt])
        rows.append({"date": dt.date().isoformat(), "year": int(dt.year),
                     "regime_lagged": trend, "volatility_lagged": volatility,
                     "tech_leadership_lagged": tech})
    return pd.DataFrame(rows)


def event_set(trades, baseline, prices, state, *, family, excluded):
    if family == "BULL_BASELINE":
        return prepared_events(baseline, prices, state,
                               strategy="LOGISTIC", excluded=excluded)
    if family == "BEAR_LOGISTIC":
        return prepared_events(
            trades.loc[trades["candidate_family"] == family],
            prices, state, strategy="LOGISTIC", excluded=excluded)
    if family == "BEAR_RULE":
        return prepared_events(
            trades.loc[trades["candidate_family"] == family],
            prices, state, strategy="TREND_RULE", excluded=excluded)
    raise ValueError("UNKNOWN_RESEARCH_CANDIDATE")


def compute_scenarios(spec, market, baseline_csv, bear_trades, out,
                      *, prices=None):
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    prices = prices if prices is not None else prices_from_market(market, spec)
    sessions = validate_sessions(prices)
    state = market_state(prices)
    benchmark = {s: buy_hold(prices, sessions, s)
                 for s in ("SPY", "QQQ")}
    baseline_df = pd.read_csv(baseline_csv)
    all_metrics = []
    all_equity = []
    all_executions = []
    all_annual = []
    selected_regimes = {}
    excluded_high_risk = set(spec["high_risk_shadow_only"])
    for cohort in COHORTS:
        excluded = excluded_high_risk if cohort == "EXCLUDE_HIGH_RISK" else set()
        bull = event_set(bear_trades, baseline_df, prices, state,
                         family="BULL_BASELINE", excluded=excluded)
        bear_rule = event_set(bear_trades, baseline_df, prices, state,
                              family="BEAR_RULE", excluded=excluded)
        bear_model = event_set(bear_trades, baseline_df, prices, state,
                               family="BEAR_LOGISTIC", excluded=excluded)
        candidate_map = {
            "BULL_BASELINE": bull,
            "BEAR_RULE_ONLY": bear_rule,
            "BEAR_LOGISTIC_ONLY": bear_model,
            "BULL_PLUS_BEAR_RULE": [*bull, *bear_rule],
            "BULL_PLUS_BEAR_LOGISTIC": [*bull, *bear_model],
        }
        for name, events in candidate_map.items():
            for cost in COSTS:
                scenario = f"{name}__{cohort}__POS{CAPACITY}__COST{int(cost)}BP"
                curve, executions, skipped = simulate(
                    events, prices, sessions, strategy=name, cohort=cohort,
                    max_positions=CAPACITY, allocation=EQUITY_FRACTION,
                    round_trip_cost_bps=cost, initial_cash=INITIAL_CASH
                )
                metrics = performance(curve)
                metrics.update({
                    "scenario": scenario, "name": name,
                    "cohort": cohort, "cost_bps": cost,
                    "max_positions": CAPACITY, "target_weight": EQUITY_FRACTION,
                    "candidate_trades": len(events),
                    "executed_trades": len(executions),
                    "rejected_candidates": skipped,
                    "is_primary": cost == COSTS[0],
                    "research_only": True, "approved_live": False,
                })
                all_metrics.append(metrics)
                for dt, r in curve.iterrows():
                    all_equity.append({
                        "scenario": scenario, "date": dt.date().isoformat(),
                        "equity": float(r["equity"]), "daily_return": float(r["daily_return"]),
                        "drawdown": float(r["drawdown"]), "cash": float(r["cash"]),
                        "active_positions": int(r["active_positions"]),
                        "gross_exposure": float(r["gross_exposure"])
                    })
                if not executions.empty:
                    all_executions.extend({
                        "scenario": scenario, **item
                    } for item in executions.to_dict("records"))
                all_annual.extend({
                    "scenario": scenario, "year": year, "net_return": float(value)
                } for year, value in metrics["calendar_year_returns"].items())
                if cost == COSTS[0]:
                    selected_regimes[scenario] = {
                        "signal_entries": trade_group_stats(executions),
                        "daily_market_context": conditional_daily_stats(curve, state),
                    }
    return (pd.DataFrame(all_metrics), pd.DataFrame(all_equity),
            pd.DataFrame(all_executions), pd.DataFrame(all_annual),
            selected_regimes, benchmark, sessions, state)


def decay_table(baseline_trades, state, sessions, bear_coverage):
    """Observation-level coverage and completed trade response by prior regime.

    No counterfactual trade imputation for signals disallowed under prior gate.
    """
    coverage = regime_days(state, sessions)
    by_year = []
    for year, year_days in coverage.groupby("year"):
        candidates = baseline_trades.loc[
            pd.to_datetime(baseline_trades["entry_date"]).dt.year.eq(year)]
        oos = bear_coverage[bear_coverage["year"] == year]
        by_year.append({
            "year": int(year),
            "market_sessions": int(len(year_days)),
            "bull_lagged_sessions": int((year_days["regime_lagged"] == "BULL").sum()),
            "bear_lagged_sessions": int((year_days["regime_lagged"] == "BEAR").sum()),
            "vix_20_30_sessions": int((year_days["volatility_lagged"] == "VIX_20_30").sum()),
            "vix_ge30_sessions": int((year_days["volatility_lagged"] == "VIX_GE30").sum()),
            "baseline_oos_entries_all_symbols": int(len(candidates)),
            "observed_bear_label_rows_all_symbols": int(oos["bear_gate_rows"].sum()),
            "bear_rule_qualified_all_symbols": int(oos["rule_qualified_rows"].sum()),
            "bear_ml_qualified_all_symbols": int(oos["logistic_qualified_rows"].sum()),
            "note": "Signal-day regime lagged one session; candidate rows overlap across symbols."
        })
    return pd.DataFrame(by_year), coverage


def run(spec, market, features, base_trades, portfolio_summary, out):
    # Prevent implicit tuning of this predeclared OOS study when upstream
    # baseline risk parameters are changed independently.
    if (spec["round_trip_cost_bps"] != 20
            or spec["first_test_year"] != 2024
            or spec["probability_threshold"] != 0.60):
        raise RuntimeError("BEAR_STUDY_REQUIRES_FROZEN_DAILY20_BASELINE")
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    bear_trades, coverage, folds = make_bear_candidates(spec, market, features)
    baseline = pd.read_csv(base_trades)
    prices = prices_from_market(market, spec)
    scenarios, curves, fills, annual, regimes, benchmark, sessions, state = compute_scenarios(
        spec, market, base_trades, bear_trades, out, prices=prices
    )
    if scenarios.shape[0] != len(SCENARIOS) * len(COHORTS) * len(COSTS):
        raise RuntimeError("NOT_20_FIXED_BEAR_SCENARIOS")
    if curves.shape[0] != len(sessions) * len(scenarios):
        raise RuntimeError("DAILY_EQUITY_LENGTH_MISMATCH")

    # Reproduce the existing unchanged bull baseline scenario exactly.
    import json
    previous = json.loads(Path(portfolio_summary).read_text())
    for cohort in COHORTS:
        case = scenarios[(scenarios["name"] == "BULL_BASELINE")
                         & (scenarios["cohort"] == cohort)
                         & (scenarios["cost_bps"] == COSTS[0])].iloc[0]
        expected = next(x for x in previous["primary_scenarios"]
                        if x["scenario"] == f"LOGISTIC__{cohort}__POS5__COST20BP")
        if not (np.isclose(case["total_return"], expected["total_return"], rtol=0, atol=1e-9)
                and np.isclose(case["max_close_drawdown"], expected["max_close_drawdown"],
                               rtol=0, atol=1e-9)
                and int(case["executed_trades"]) == int(expected["executed_trades"])):
            raise RuntimeError("BULL_PORTFOLIO_REPRODUCTION_FAILED")

    coverage_days, sessions_by_day = decay_table(baseline, state, sessions, coverage)
    bear_trades.to_csv(output / "bear_oos_trades.csv", index=False)
    coverage.to_csv(output / "bear_model_coverage.csv", index=False)
    scenarios.drop(columns=["calendar_year_returns", "rejected_candidates"]).to_csv(
        output / "regime_scenarios.csv", index=False)
    curves.to_csv(output / "regime_daily_equity.csv", index=False)
    fills.to_csv(output / "regime_executions.csv", index=False)
    annual.to_csv(output / "regime_annual.csv", index=False)
    coverage_days.to_csv(output / "regime_year_coverage.csv", index=False)
    sessions_by_day.to_csv(output / "regime_session_context.csv", index=False)

    summary = {
        "version": VERSION, "status": "RESEARCH_ONLY", "research_only": True,
        "live_execution": False, "tradable_strategy_approved": False,
        "fixed_pre_oos_policy": {
            "market_bear": "SPY close below SMA200 at prior session, VIX prior <=45",
            "rule": "RSI14 in [30,60] + positive return1 + improving MACD histogram",
            "ml": "Logistic(C=0.2, balanced) trained only earlier BEAR rows with 4-session purge",
            "bear_train_min": MIN_BEAR_TRAIN, "ml_probability_threshold": ML_THRESHOLD,
            "max_positions": CAPACITY, "allocation": EQUITY_FRACTION,
            "cost_bps": list(COSTS),
        },
        "oos_start": str(sessions[0].date()), "oos_end": str(sessions[-1].date()),
        "cohorts": list(COHORTS), "families": list(SCENARIOS),
        "scenario_count": len(scenarios),
        "unique_bear_oos_trades": len(bear_trades),
        "bear_trade_families": bear_trades["candidate_family"].value_counts().to_dict(),
        "scenario_results": scenarios.to_dict(orient="records"),
        "regime_attribution": regimes,
        "benchmarks": benchmark,
        "per_year_market_coverage": coverage_days.to_dict(orient="records"),
        "folds": folds,
        "warnings": [
            "Bear-rule thresholds predeclared but tested retrospectively; no strategy chosen",
            "Bull signal generator remains unchanged and has zero bear entries",
            "Bear logistic uses bear-only training rows and annual purge; scarcity may leave blank years",
            "Bull/Bear combined comparisons include signal-family switching and equal-slot conflicts",
            "Historic 2026-fixed 20-symbol universe has survivorship/selection bias",
            "QQQ/QLD overlap and simultaneous sector exposure create correlation risk",
            "EOD drawdown cannot represent intraday stop execution, opening gaps or partial fills",
            "Calendar-year equity returns are portfolio, not means of individual trades",
            "Yahoo adjusted price history may be retrospectively revised",
            "No bear challenger is approved for LIVE or strategy selection",
        ],
    }
    write_json(output / "regime_summary.json", summary)
    print(json.dumps({
        "DAILY20_BEAR_CHALLENGER": "COMPLETE",
        "oos_bear_trade_rows": len(bear_trades),
        "model_rows": int((bear_trades["candidate_family"] == "BEAR_LOGISTIC").sum()),
        "rule_rows": int((bear_trades["candidate_family"] == "BEAR_RULE").sum()),
        "scenarios": len(scenarios),
        "annual_bear_sessions": {
            str(row["year"]): row["bear_lagged_sessions"]
            for row in summary["per_year_market_coverage"]
        },
        "primary": [{
            "scenario": x["scenario"],
            "total_return": round(float(x["total_return"]), 5),
            "mdd": round(float(x["max_close_drawdown"]), 5),
            "trades": int(x["executed_trades"])
        } for x in summary["scenario_results"] if x["is_primary"]],
    }))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="research/kalman_daily20/universe.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--baseline-trades", required=True)
    parser.add_argument("--portfolio-summary", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(load_spec(args.config), args.market, args.features, args.baseline_trades,
        args.portfolio_summary, args.out)


if __name__ == "__main__":
    main()
