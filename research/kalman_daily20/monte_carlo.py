#!/usr/bin/env python3
"""Paired Monte Carlo block bootstrap of Daily20 cash-ledger equity returns.

Mandatory 2024+ research risk stress, NOT a prospective alpha confidence
statement. Uses jointly sampled daily equity returns so market-wide selloffs
and correlation between the candidate strategies and SPY/QQQ are preserved.
Returns already include capital limits/fees from portfolio and challenger.
Bootstrapping these returns does NOT re-execute a path-dependent book.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from daily20 import load_spec, write_json, market_file, load_bars

VERSION = "daily20-monte-carlo-v1"
SEED = 2601121
REPETITIONS = 2000
CHUNK = 128
BLOCKS = (1, 5, 20)
INITIAL_CAPITAL = 100_000.0
MARKETS = ("SPY", "QQQ")
MIN_SESSIONS = 252
EXPECTED_BASE = 16
EXPECTED_REGIME = 20
TRADING_DAYS = 252


def load_synchronized_curves(portfolio_csv, regime_csv, market, spec):
    datasets = []
    names = set()
    for path, count in ((portfolio_csv, EXPECTED_BASE),
                        (regime_csv, EXPECTED_REGIME)):
        df = pd.read_csv(path, parse_dates=["date"])
        required = {"scenario", "date", "daily_return", "equity"}
        if not required.issubset(df.columns):
            raise RuntimeError("MONTE_CARLO_MISSING_EQUITY_COLUMNS")
        if df["scenario"].nunique() != count:
            raise RuntimeError("MONTE_CARLO_WRONG_SCENARIO_COUNT")
        if df.duplicated(["date", "scenario"]).any():
            raise RuntimeError("MONTE_CARLO_DUPLICATE_SESSION")
        df["date"] = df["date"].dt.normalize()
        if names.intersection(df["scenario"]):
            raise RuntimeError("MONTE_CARLO_DUPLICATE_STRATEGY_NAME")
        names.update(df["scenario"])
        datasets.append(df)
    all_rows = pd.concat(datasets, ignore_index=True)
    wide = all_rows.pivot(index="date", columns="scenario", values="daily_return").sort_index()
    if wide.isna().any().any() or len(wide) < MIN_SESSIONS:
        raise RuntimeError("MONTE_CARLO_INCOMPLETE_DAILY_CASH_LEDGER")
    expected_n = (EXPECTED_BASE + EXPECTED_REGIME)
    if wide.shape[1] != expected_n:
        raise RuntimeError("MONTE_CARLO_MISSING_STRATEGY")
    if wide.index.has_duplicates or not wide.index.is_monotonic_increasing:
        raise RuntimeError("MONTE_CARLO_CALENDAR_INVALID")
    for symbol in MARKETS:
        close = load_bars(market_file(market, symbol))["close"].reindex(wide.index)
        if close.isna().any() or (close <= 0).any():
            raise RuntimeError("MONTE_CARLO_MISSING_BENCHMARK:" + symbol)
        # Baseline first date is a zero-return starting point; subsequent
        # sessions use price changes on the same dates as all strategies.
        observed = close.pct_change(fill_method=None).fillna(0.0)
        wide["BENCHMARK_" + symbol] = observed
    if not np.isfinite(wide.to_numpy(dtype=float)).all():
        raise RuntimeError("MONTE_CARLO_NONFINITE_DAILY_RETURNS")
    if (wide <= -1.0).any().any():
        raise RuntimeError("MONTE_CARLO_INVALID_TOTAL_EQUITY_LOSS")
    return wide


def validate_original_curves(wide, p_portfolio, p_regime):
    """Daily returns must reconstruct each unbootstrapped terminal equity."""
    for path in (p_portfolio, p_regime):
        df = pd.read_csv(path)
        for scenario, group in df.groupby("scenario"):
            rows = group.sort_values("date")
            calc = INITIAL_CAPITAL * float(np.prod(1.0 + wide[scenario].to_numpy()))
            expected = float(rows["equity"].iloc[-1])
            if not np.isclose(calc, expected, rtol=2e-8, atol=1e-5):
                raise RuntimeError("MONTE_CARLO_LEDGER_RETURNS_MISMATCH:" + scenario)


def sample_joint_indices(rng, dates, *, block, size, stratify_year=True):
    """Circular moving blocks, sampled with replacement by entire date row.

    Stratification retains each study calendar year's approximate count and
    volatility regime. Blocks are not allowed to cross year boundaries.
    One common index matrix applies to every portfolio and both benchmarks.
    """
    if block < 1 or size < 1:
        raise ValueError("INVALID_MC_DRAW_SETTINGS")
    timeline = pd.DatetimeIndex(dates)
    if timeline.has_duplicates or not timeline.is_monotonic_increasing:
        raise RuntimeError("MC_DATE_SEQUENCE_NOT_MONOTONIC")
    n = len(timeline)
    partitions = ([
        np.flatnonzero(timeline.year == year).astype(np.int32)
        for year in sorted(set(timeline.year))
    ] if stratify_year else [np.arange(n, dtype=np.int32)])
    out = np.empty((size, n), dtype=np.int32)
    offset = 0
    for part in partitions:
        m = len(part)
        if not m:
            continue
        # Partial first/last calendar years can have fewer sessions than
        # the requested block. Preserve their actual sample counts instead
        # of failing the daily pipeline; disclose truncation in the report.
        effective_block = min(block, m)
        starts = rng.integers(0, m, size=(size, (m + effective_block - 1) // effective_block))
        within = (starts[:, :, None] +
                  np.arange(effective_block, dtype=np.int32)[None, None, :]) % m
        sampled = part[within.reshape(size, -1)[:, :m]]
        out[:, offset:offset + m] = sampled
        offset += m
    if offset != n or (out < 0).any() or (out >= n).any():
        raise RuntimeError("MC_SAMPLING_CORRUPTED_CALENDAR")
    return out


def portfolio_path_metrics(sample_returns):
    """Vectorized over resamples and series. Peak includes starting $1."""
    if sample_returns.ndim != 3:
        raise ValueError("MC_EXPECTS_SIMULATION_DATE_SERIES")
    simulated = np.cumprod(1.0 + sample_returns, axis=1)
    initial = np.ones((simulated.shape[0], 1, simulated.shape[2]))
    values = np.concatenate((initial, simulated), axis=1)
    peak = np.maximum.accumulate(values, axis=1)
    drawdowns = values / peak - 1
    return simulated[:, -1, :] - 1, np.min(drawdowns, axis=1)


def one_configuration(wide, *, block, repetitions=REPETITIONS, seed=SEED,
                      chunksize=CHUNK):
    """Paired block-resampling across the exact same sessions and strategies."""
    if repetitions < 200 or chunksize < 1:
        raise ValueError("INSUFFICIENT_MC_REPLICATIONS")
    n = len(wide)
    cols = list(wide.columns)
    values = wide.to_numpy(dtype=np.float64)
    rng = np.random.default_rng(seed + block * 10_007)
    rows = []
    results, drawdowns = [], []
    for offset in range(0, repetitions, chunksize):
        size = min(chunksize, repetitions - offset)
        sampled = sample_joint_indices(
            rng, wide.index, block=block, size=size, stratify_year=True
        )
        terminal, worst = portfolio_path_metrics(values[sampled, :])
        if not (np.isfinite(terminal).all() and np.isfinite(worst).all()):
            raise RuntimeError("NONFINITE_MC_OUTCOME")
        results.append(terminal)
        drawdowns.append(worst)
    final = np.concatenate(results, axis=0)
    mdd = np.concatenate(drawdowns, axis=0)
    spy = cols.index("BENCHMARK_SPY")
    qqq = cols.index("BENCHMARK_QQQ")
    for col_index, name in enumerate(cols):
        t = final[:, col_index]
        d = mdd[:, col_index]
        alpha_spy = t - final[:, spy]
        alpha_qqq = t - final[:, qqq]
        worst_threshold = np.quantile(t, 0.05)
        rows.append({
            "scenario": name,
            "block_length": block,
            "n_resamples": int(repetitions),
            "seed": int(seed),
            "n_sessions": int(n),
            "return_p05": float(np.quantile(t, .05)),
            "return_median": float(np.median(t)),
            "return_p95": float(np.quantile(t, .95)),
            "expected_return_mean": float(np.mean(t)),
            "loss_probability": float(np.mean(t < 0.0)),
            "return_cvar_05": float(np.mean(t[t <= worst_threshold])),
            "mdd_p05_worst": float(np.quantile(d, .05)),
            "mdd_median": float(np.median(d)),
            "mdd_p95_best": float(np.quantile(d, .95)),
            "mdd_at_least_20pct_probability": float(np.mean(d <= -0.20)),
            "mdd_at_least_30pct_probability": float(np.mean(d <= -0.30)),
            "probability_underperform_spy": float(np.mean(alpha_spy < 0.0)),
            "probability_underperform_qqq": float(np.mean(alpha_qqq < 0.0)),
            "alpha_spy_p05": float(np.quantile(alpha_spy, .05)),
            "alpha_spy_median": float(np.median(alpha_spy)),
            "alpha_qqq_median": float(np.median(alpha_qqq)),
            "status": "HISTORICAL_RESAMPLING_ONLY",
            "approved_live": False,
        })
    return pd.DataFrame(rows)


def run(config, market, portfolio_csv, regime_csv, out,
        *, repetitions=REPETITIONS, seed=SEED):
    spec = load_spec(config)
    if spec["live_execution"] is not False:
        raise RuntimeError("MONTE_CARLO_LIVE_FORBIDDEN")
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    wide = load_synchronized_curves(portfolio_csv, regime_csv, market, spec)
    validate_original_curves(wide, portfolio_csv, regime_csv)
    mc = pd.concat([
        one_configuration(wide, block=block, repetitions=repetitions, seed=seed)
        for block in BLOCKS
    ], ignore_index=True)
    expected = (EXPECTED_BASE + EXPECTED_REGIME + len(MARKETS)) * len(BLOCKS)
    if len(mc) != expected or mc.isna().any().any():
        raise RuntimeError("INCOMPLETE_MC_EVIDENCE")
    for symbol in MARKETS:
        if f"BENCHMARK_{symbol}" not in set(mc["scenario"]):
            raise RuntimeError("MC_BENCHMARK_GONE:" + symbol)
    path = root / "monte_carlo_scenarios.csv"
    mc.to_csv(path, index=False)
    primary = [
        "BULL_BASELINE__ALL_20__POS5__COST20BP",
        "BULL_PLUS_BEAR_LOGISTIC__EXCLUDE_HIGH_RISK__POS5__COST20BP",
        "BEAR_LOGISTIC_ONLY__ALL_20__POS5__COST20BP",
        "LOGISTIC__ALL_20__POS5__COST20BP",
        "BENCHMARK_SPY", "BENCHMARK_QQQ",
    ]
    selected = mc[(mc["scenario"].isin(primary)) & mc["block_length"].eq(20)]
    if len(selected) != len(primary):
        raise RuntimeError("MONTE_CARLO_PRIMARY_CASE_MISSING")
    baseline = pd.DataFrame({
        "scenario": wide.columns,
        "observed_total_return": (1.0 + wide).prod(axis=0).to_numpy() - 1.0,
        "sessions": len(wide),
    })
    baseline.to_csv(root / "monte_carlo_observed_baseline.csv", index=False)
    summary = {
        "version": VERSION,
        "status": "HISTORICAL_RESAMPLING_ONLY",
        "research_only": True,
        "approved_live": False,
        "model_selection_allowed": False,
        "future_oos_validated": False,
        "not_a_forecast_probability": True,
        "sampling_method": "paired_circular_moving_block_bootstrap_year_stratified",
        "block_lengths": list(BLOCKS),
        "partial_year_block_truncation": {
            str(y): {str(block): int(min(block, (wide.index.year == y).sum()))
                     for block in BLOCKS}
            for y in sorted(set(wide.index.year))
        },
        "iid_diagnostic_block_length": 1,
        "replications_per_block": repetitions,
        "seed": seed,
        "sessions": len(wide),
        "first_session": str(wide.index.min().date()),
        "last_session": str(wide.index.max().date()),
        "strategy_scenarios": EXPECTED_BASE + EXPECTED_REGIME,
        "benchmarks": list(MARKETS),
        "scenario_rows": len(mc),
        "primary_block20": selected.to_dict("records"),
        "warnings": [
            "Historical, nonstationary 2024-26 regime mix was already examined; Monte Carlo CANNOT create new holdout evidence.",
            "Resamples preserve same-day joint market/strategy movement and within-block clusters, but break longer dependence.",
            "Year-stratified returns condition on observed years and are NOT a probability for future independent years.",
            "Block length 1 is IID diagnostic and may underestimate long-horizon drawdowns.",
            "Blocks are truncated to available sessions in partial calendar years; consult partial_year_block_truncation.",
            "Daily equity returns reflect frozen finite-cash portfolio, yet resampling does NOT rerun path-dependent position sizing.",
            "Existing Yahoo adjusted daily prices, not SIP, and broker execution is hypothetical.",
            "No live order, no strategy auto-promotion, no proof of positive expected return.",
        ],
    }
    write_json(root / "monte_carlo_summary.json", summary)
    print(json.dumps({"DAILY20_MONTE_CARLO": {
        "status": "COMPLETE", "sessions": len(wide),
        "strategy_scenarios": EXPECTED_BASE + EXPECTED_REGIME,
        "rows": len(mc), "replications_per_block": repetitions,
        "block_lengths": list(BLOCKS),
        "block20_primary": [
            {"scenario": x["scenario"],
             "loss_probability": round(x["loss_probability"], 4),
             "mdd_p05_worst": round(x["mdd_p05_worst"], 4),
             "underperform_spy_probability":
                 round(x["probability_underperform_spy"], 4)}
            for x in summary["primary_block20"]
        ]
    }}))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="research/kalman_daily20/universe.json")
    parser.add_argument("--market", required=True)
    parser.add_argument("--portfolio", required=True)
    parser.add_argument("--regime", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(args.config, args.market, args.portfolio, args.regime, args.out)


if __name__ == "__main__":
    main()
