#!/usr/bin/env python3
"""10,000 independent-uniform randomly proposed *joint* QLD policies + 1 control.

Research only. The uniform distribution is on raw per-axis levels. Invalid
risk/credit bounds are rejected, inactive knobs normalized, duplicates rejected.
No search outcome or prior 800-sweep result influences candidate sampling.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research.kalman_integrated_regime import run as base
from research.kalman_integrated_regime import joint_policy as joint


def uniform_random_policies(n=10000, seed=20261101):
    if n <= 0:
        raise ValueError("POSITIVE_RANDOM_COUNT_REQUIRED")
    rng = np.random.default_rng(seed)
    baseline = joint.normalize(joint.BASELINE)
    seen = {joint.policy_id(baseline)}
    result = [baseline]  # extra comparator, never counted among 10,000 random policies
    proposed = 0
    rejected_invalid = 0
    rejected_duplicate = 0
    keys = list(joint.AXES)
    while len(result) <= n:
        proposed += 1
        if proposed > max(100 * n, 1000):
            raise RuntimeError("REJECTION_LIMIT_EXCEEDED")
        # Every raw axis independently receives a discrete uniform draw.
        p = {k: joint.AXES[k][int(rng.integers(len(joint.AXES[k])))] for k in keys}
        if not joint.policy_valid(p):
            rejected_invalid += 1
            continue
        p = joint.normalize(p)  # Inactive parameter values are not distinct policies.
        uid = joint.policy_id(p)
        if uid in seen:
            rejected_duplicate += 1
            continue
        seen.add(uid)
        result.append(p)
    return result, {
        "random_candidates_accepted": n,
        "additional_unrandomized_baseline": 1,
        "raw_proposals": proposed,
        "invalid_rejections": rejected_invalid,
        "duplicate_or_baseline_rejections": rejected_duplicate,
        "seed": seed,
        "draw": "IID_UNIFORM_PER_RAW_AXIS_LEVEL; CONDITIONAL_REJECTION",
        "outcome_blind": True,
        "all_40_axes_sampled": True
    }


def run_shard(daily, intraday, market_zip, n, seed, shard, shards):
    if shards <= 0 or not 0 <= shard < shards:
        raise ValueError("BAD_SHARD")
    policies, generator = uniform_random_policies(n, seed)
    prices = base.read_prices(daily)
    features = base.build_features(prices, base.read_market_zip(market_zip))
    x = base.read_15m(intraday)
    complete, coverage = base.complete_sessions(x, prices.index)
    events = base.label_events(prices.index, complete)
    signals = {y: joint.fit_probabilities(features, events, y) for y in (2025, 2026)}
    dates = list(pd.DatetimeIndex(prices.index))
    rows = []
    for k, policy in enumerate(policies):
        if k % shards != shard:
            continue
        for year in (2025, 2026):
            for model, probability in signals[year].items():
                result = joint.simulate_portfolio(policy, probability, features, complete, dates, year)
                rows.append({"config_index": k,
                             "policy_id": joint.policy_id(policy),
                             "year": year, "model": model,
                             "params": policy, **result})
    return {
        "schema": "qld-random10k-joint-shard-v1",
        "status": "EXPLORATORY_NOT_LIVE_AUTHORIZED",
        "configs_total": n + 1,
        "random_configs": n,
        "baseline_configs": 1,
        "configs_in_shard": sum(k % shards == shard for k in range(n + 1)),
        "shard": shard, "shards": shards,
        "generator": generator,
        "dimensions": len(joint.AXES),
        "full_factorial_count": int(np.prod(np.array([len(v) for v in joint.AXES.values()], dtype=object))),
        "pairwise_coverage": joint.pairwise_coverage(policies),
        "not_exhaustive": True,
        "not_out_of_sample_policy_selection": True,
        "model_probabilities_refitted_by_year_without_test_training": True,
        "no_live_changes": True,
        "rth_complete_sessions": coverage["complete"],
        "rows": rows,
    }


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--daily", required=True)
    a.add_argument("--intraday", required=True)
    a.add_argument("--market-zip", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--configs", type=int, default=10000)
    a.add_argument("--shard", type=int, default=0)
    a.add_argument("--shards", type=int, default=4)
    a.add_argument("--seed", type=int, default=20261101)
    args = a.parse_args()
    result = run_shard(args.daily, args.intraday, args.market_zip,
                       args.configs, args.seed, args.shard, args.shards)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"joint_shard_{args.shard}.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print("RANDOM10K_SHARD " + json.dumps({
        k: v for k, v in result.items() if k != "rows"
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
