#!/usr/bin/env python3
"""Aggregate *joint policy* shards. Descriptive search only: no LIVE winner."""
import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import statistics

from research.kalman_integrated_regime.joint_policy import (
    AXES, BASELINE, interaction_screen, policy_id,
)


def aggregate(shards, expected_configs):
    items = [json.loads(Path(f).read_text()) for f in shards]
    if not items:
        raise ValueError("NO_SHARDS")
    total_shards = items[0]["shards"]
    if len(items) != total_shards:
        raise ValueError("NOT_ALL_SHARDS_PRESENT")
    if {v["shard"] for v in items} != set(range(total_shards)):
        raise ValueError("DUPLICATE_OR_MISSING_SHARD")
    if any(v["configs_total"] != expected_configs or v["shards"] != total_shards for v in items):
        raise ValueError("SHARD_MANIFEST_MISMATCH")
    rows = sum((v["rows"] for v in items), [])
    expected = expected_configs * 2 * 2
    if len(rows) != expected:
        raise ValueError(f"MISSING_CONFIG_MODEL_YEAR_ROWS:{len(rows)}:{expected}")
    grouped = defaultdict(dict)
    allids = set()
    for r in rows:
        key = (r["policy_id"], r["config_index"])
        k = (r["year"], r["model"])
        if k in grouped[key] or r["policy_id"] != policy_id(r["params"]):
            raise ValueError("DUPLICATE_OR_MISMATCHED_ROW")
        grouped[key][k] = r
        allids.add(r["policy_id"])
    if len(grouped) != expected_configs or len(allids) != expected_configs:
        raise ValueError("DUPLICATE_OR_MISSING_POLICIES")
    wanted = {(2025, "price_only"), (2026, "price_only"),
              (2025, "integrated_regime"), (2026, "integrated_regime")}
    if any(set(x) != wanted for x in grouped.values()):
        raise ValueError("NOT_FULL_PAIRED_COHORT")
    baseline = next((group for group in grouped.values()
                     if group[(2025, "integrated_regime")]["params"] == BASELINE), None)
    if baseline is None:
        raise ValueError("BASELINE_MISSING")
    baseline_metrics = {
        f"{year}_{model}": baseline[(year, model)]["return_pct"]
        for year, model in sorted(wanted)}
    summaries = []
    for (uid, idx), group in grouped.items():
        for model in ("price_only", "integrated_regime"):
            y25, y26 = group[(2025, model)], group[(2026, model)]
            b25, b26 = baseline[(2025, model)], baseline[(2026, model)]
            eligible = min(y25["trades"], y26["trades"]) >= 15
            row = {
                "policy_id": uid, "config_index": idx, "model": model,
                "params": y25["params"], "qualified_min_15_trades_each_year": eligible,
                "return_2025_pct": y25["return_pct"],
                "return_2026_ytd_pct": y26["return_pct"],
                "mdd_2025_pct": y25["mdd_daily_mark_pct"],
                "mdd_2026_ytd_pct": y26["mdd_daily_mark_pct"],
                "trades_2025": y25["trades"], "trades_2026_ytd": y26["trades"],
                "delta_2025_vs_baseline_pp": round(y25["return_pct"]-b25["return_pct"], 5),
                "delta_2026_vs_baseline_pp": round(y26["return_pct"]-b26["return_pct"], 5),
                "both_years_improve": bool(y25["return_pct"] > b25["return_pct"] and
                                           y26["return_pct"] > b26["return_pct"]),
                "worst_year_return_pct": min(y25["return_pct"], y26["return_pct"]),
                "worst_year_mdd_pct": min(y25["mdd_daily_mark_pct"], y26["mdd_daily_mark_pct"]),
                "both_years_positive": bool(y25["return_pct"] > 0 and y26["return_pct"] > 0),
            }
            summaries.append(row)
    rankings = {}
    for model in ("price_only", "integrated_regime"):
        eligible = [r for r in summaries if r["model"] == model and r["qualified_min_15_trades_each_year"]]
        ranked = sorted(eligible, key=lambda r: (r["worst_year_return_pct"], r["worst_year_mdd_pct"]), reverse=True)
        rankings[model] = {
            "qualified_count": len(eligible),
            "fraction_both_years_improve": round(
                sum(r["both_years_improve"] for r in eligible)/len(eligible), 5) if eligible else None,
            "fraction_both_years_positive": round(
                sum(r["both_years_positive"] for r in eligible)/len(eligible), 5) if eligible else None,
            "top_exploratory_by_worst_year": ranked[:20],
            "baseline_reference": next((r for r in summaries if r["model"]==model and r["config_index"]==0), None),
        }
    interactions = {f"{year}_{model}": interaction_screen(rows, year, model)
                    for year, model in wanted}
    return {
        "schema": "kalman-qld-joint-policy-aggregate-v1",
        "status": "EXPLORED_NOT_PIT_VALIDATED",
        "configs_evaluated": expected_configs,
        "full_joint_strategies_per_model_year": expected_configs,
        "total_portfolio_simulations": len(rows),
        "dimensions": len(AXES),
        "axes": {key: list(vals) for key, vals in AXES.items()},
        "full_factorial_count": items[0]["full_factorial_count"],
        "pairwise_coverage": items[0]["pairwise_coverage"],
        "baseline_return_pct": baseline_metrics,
        "selection_caveat": "All 2025/2026 results are exploratory because policy configurations were compared on those test years; apparent winners suffer multiple-testing/data-snooping bias. No independent out-of-sample policy validation.",
        "interaction_caveat": "Descriptive random mixed-level factorial contrasts are neither causal effects nor statistical significance.",
        "cost_caveat": "Fixed 10bp side fee plus slippage scenarios, gap/stop worst-case fills, adjusted 15m bars; realistic executable fills not independently verified.",
        "all_live_execution_unchanged": True,
        "hold_live": True,
        "rankings": rankings,
        "interactions": interactions,
        "rows": summaries,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source", required=True, help="Folder containing joint_shard_*.json")
    p.add_argument("--configs", type=int, default=800)
    p.add_argument("--out", required=True)
    a=p.parse_args()
    fs=sorted(Path(a.source).rglob("joint_shard_*.json"))
    report=aggregate(fs, a.configs)
    output=Path(a.out)
    output.mkdir(parents=True,exist_ok=True)
    (output/"joint_all_results.json").write_text(json.dumps(report,ensure_ascii=False,indent=None)+"\n")
    (output/"joint_leaderboard_summary.json").write_text(json.dumps(
        {k:v for k,v in report.items() if k!="rows"},ensure_ascii=False,indent=2)+"\n")
    print("JOINT_AGGREGATE "+json.dumps({
        "configs":report["configs_evaluated"],
        "dimensions":report["dimensions"],
        "full_factorial_count":report["full_factorial_count"],
        "pairwise_coverage":report["pairwise_coverage"],
        "baseline_return_pct":report["baseline_return_pct"],
        "rankings":{k:{"qualified_count":v["qualified_count"],
                       "fraction_both_years_improve":v["fraction_both_years_improve"],
                       "fraction_both_years_positive":v["fraction_both_years_positive"],
                       "top3":v["top_exploratory_by_worst_year"][:3]}
                    for k,v in report["rankings"].items()},
        "hold_live": True},ensure_ascii=False))


if __name__=="__main__":
    main()
