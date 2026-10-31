#!/usr/bin/env python3
"""Research-only 40-axis conditional stratified JOINT policy experiment.

Outcome blind: the conditional design caps simultaneous restrictive signal
filters at four, but varies ALL 40 parameters across the candidate population.
Always compare each complete policy under its native allocation and a common
50% cash allocation, to expose size-driven apparent improvements.

This is a follow-up exploratory study; historical 2025/2026 policies are NOT
out of sample for *policy selection*. No LIVE authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kalman_integrated_regime import run as base
from research.kalman_integrated_regime import joint_policy as joint

# These 20 groups are signal-gating knobs, distinct from trade management.
# For each randomly sampled joint execution configuration, uniformly choose
# 0-4 active gate families without replacement. This does not tune to returns.
GATES = {
    "confidence": ("confidence", [0.55, 0.60, 0.65]),
    "vix_lower": ("vix_min", [12., 15., 18.]),
    "vix_upper": ("vix_max", [20., 25., 35.]),
    "qqq_trend": ("trend", ["r5", "r20", "both"]),
    "qld_trend": ("qld_r5_gate", ["positive", "negative"]),
    "vol_upper": ("vol_cap", [.02, .03, .04]),
    "vol_lower": ("vol_floor", [.0075, .015, .0225]),
    "credit_lower": ("credit_floor", [-.01, 0.]),
    "credit_upper": ("credit_cap", [0., .01]),
    "tnx_upper": ("tnx_cap", [4., 5., 6.]),
    "vix_change_upper": ("vix_change_cap", [.1, .2]),
    "sector_lower": ("smh_spy_floor", [-.02, 0.]),
    "qqq_20_upper": ("qqq_r20_cap", [.05, .1]),
    "qqq_5_upper": ("qqq_r5_cap", [.025, .05]),
    "qld_5_abs": ("qld_r5_abs_cap", [.03, .06]),
    "gap_up_cap": ("gap_cap", [.01, .02, .04]),
    "gap_down_cap": ("gap_down_cap", [.01, .02, .04]),
    "gap_up_floor": ("gap_up_floor", [.005, .01, .02]),
    "prior_candle_range": ("prior_bar_range_cap", [.01, .02, .04]),
    "monthly_throttle": ("max_month", [2, 4, 8]),
}
assert len(GATES) == 20
assert len(set(axis for axis, vals in GATES.values())) == 20
assert all(a in joint.AXES and set(vals).issubset(set(joint.AXES[a])) for a, vals in GATES.values())
MANAGEMENT = tuple(k for k in joint.AXES if k not in {axis for axis, _ in GATES.values()})
assert len(MANAGEMENT) == 20
# Distinct levels: maximum 4 simultaneous gates. A zero-gate configuration
# can still have a classifier threshold of 0.45 or 0.50.
GATE_BUDGETS = (0, 1, 2, 3, 4)


def generate_structured(n=10000, seed=20261102):
    """Exactly N unique effective joint policies + a separate fixed control.

    We avoid the overfiltering pathologies observed with IID random 40 axes,
    but DO NOT optimize against any observed trade outcomes. The gate-budget
    design is precommitted.
    """
    if n <= 0 or n % len(GATE_BUDGETS):
        raise ValueError("CONFIG_COUNT_MUST_BE_POSITIVE_MULTIPLE_OF_FIVE")
    rng = np.random.default_rng(seed)
    accepted = [joint.normalize(joint.BASELINE)]
    seen = {joint.policy_id(accepted[0])}
    budget_success = Counter()
    attempts = 0
    invalid = 0
    duplicate = 0
    # Rejection sampling by precommitted filter-budget stratum, ensuring
    # equal allocation instead of favoring trivially low-activity policies.
    for tier in GATE_BUDGETS:
        target = n // len(GATE_BUDGETS)
        while budget_success[tier] < target:
            attempts += 1
            if attempts > n * 100:
                raise RuntimeError("STRATIFIED_GENERATOR_EXHAUSTED")
            p = dict(joint.BASELINE)
            for key in MANAGEMENT:
                p[key] = joint.AXES[key][int(rng.integers(len(joint.AXES[key])))]
            p["confidence"] = [0.45, .5][int(rng.integers(2))]
            active = list(rng.choice(list(GATES), size=tier, replace=False))
            for label in active:
                axis, choices = GATES[label]
                p[axis] = choices[int(rng.integers(len(choices)))]
            if not joint.policy_valid(p):
                invalid += 1
                continue
            p = joint.normalize(p)
            uid = joint.policy_id(p)
            if uid in seen:
                duplicate += 1
                continue
            seen.add(uid)
            accepted.append(p)
            budget_success[tier] += 1
    return accepted, {
        "schema": "qld-40axis-stratified-generation-v1",
        "precommitted_random_seed": seed,
        "outcome_blind": True,
        "n_random_strategies": n,
        "baseline_extra": 1,
        "all_40_axes_mutable_across_design": True,
        "execution_axes": len(MANAGEMENT),
        "gating_axes": len(GATES),
        "gate_budget_counts": {str(k): budget_success[k] for k in GATE_BUDGETS},
        "invalid_proposals": invalid,
        "duplicate_proposals": duplicate,
        "total_proposals": attempts,
        "not_uniform_over_full_40dim_space": True,
        "not_out_of_sample_policy_selection": True,
    }


def active_budget(policy):
    """Count filter-gates enabled, not unrelated money-management dimensions."""
    return sum(policy[key] != joint.BASELINE[key] for key, _ in GATES.values())


def run_shard(daily, intraday, market_zip, n, seed, shard, shards):
    if shards <= 0 or not 0 <= shard < shards:
        raise ValueError("BAD_SHARD")
    policies, generator = generate_structured(n, seed)
    prices = base.read_prices(daily)
    features = base.build_features(prices, base.read_market_zip(market_zip))
    x = base.read_15m(intraday)
    complete, coverage = base.complete_sessions(x, prices.index)
    events = base.label_events(prices.index, complete)
    signals = {y: joint.fit_probabilities(features, events, y) for y in (2025, 2026)}
    dates = list(pd.DatetimeIndex(prices.index))
    rows = []
    for index, policy in enumerate(policies):
        if index % shards != shard:
            continue
        for year in (2025, 2026):
            for model, probabilities in signals[year].items():
                native = joint.simulate_portfolio(policy, probabilities, features, complete, dates, year)
                # Re-run the SAME joint non-size policy with 50% cash allocation:
                # cost, fills and signals recomputed, not return scaled from native.
                controlled = dict(policy, size=.5, risk_budget=0.)
                fixed = joint.simulate_portfolio(controlled, probabilities, features, complete, dates, year)
                if native["trades"] != fixed["trades"]:
                    raise AssertionError("SIZE_ONLY_CHANGED_SIGNAL_OR_TRADE_COUNT")
                rows.append({
                    "config_index": index,
                    "policy_id": joint.policy_id(policy),
                    "year": year, "model": model, "params": policy,
                    "active_filter_gates": active_budget(policy),
                    **native,
                    "matched_50pct_return_pct": fixed["return_pct"],
                    "matched_50pct_mdd_pct": fixed["mdd_daily_mark_pct"],
                    "matched_50pct_trades": fixed["trades"],
                })
    return {
        "schema": "qld40-stratified-joint-shard-v1",
        "status": "EXPLORATORY_HOLD_LIVE",
        "configs_total": n + 1,
        "structured_candidates": n, "baseline_control": 1,
        "configs_in_shard": sum(k % shards == shard for k in range(n + 1)),
        "shard": shard, "shards": shards, "generator": generator,
        "dimensions": len(joint.AXES),
        "pairwise_coverage": joint.pairwise_coverage(policies),
        "full_factorial_count": int(np.prod(np.array([len(v) for v in joint.AXES.values()], dtype=object))),
        "rth_complete_sessions": coverage["complete"],
        "matched_risk_study": "RERUN_POLICY_AT_FIXED_50PCT_CASH_SIZE_RISK_BUDGET_DISABLED",
        "not_independent_forward_OOS": True,
        "no_live_changes": True,
        "rows": rows,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--daily", required=True)
    p.add_argument("--intraday", required=True)
    p.add_argument("--market-zip", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--configs", type=int, default=10000)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--seed", type=int, default=20261102)
    a = p.parse_args()
    result = run_shard(a.daily, a.intraday, a.market_zip, a.configs, a.seed, a.shard, a.shards)
    output = Path(a.out)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"joint_shard_{a.shard}.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("STRUCTURED40_SHARD " + json.dumps({k:v for k,v in result.items() if k!="rows"},
                                               ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
