#!/usr/bin/env python3
"""Complete structured-40 search report, including common 50% cash sizing.

All comparisons are exploratory in historical years used for the search.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from research.kalman_integrated_regime.joint_report import aggregate


def summarize_structured(paths, expected_configs):
    items = [json.loads(Path(path).read_text()) for path in paths]
    if not items or any("generator" not in a for a in items):
        raise ValueError("MISSING_GENERATOR_PROVENANCE")
    generations = [json.dumps(x["generator"], sort_keys=True) for x in items]
    if len(set(generations)) != 1:
        raise ValueError("GENERATOR_DISAGREES_BETWEEN_SHARDS")
    if any(x.get("structured_candidates") != expected_configs - 1 or
           x.get("baseline_control") != 1 for x in items):
        raise ValueError("MISSING_STRUCTURED_COHORT_METADATA")
    main = aggregate(paths, expected_configs)
    rows = [r for item in items for r in item["rows"]]
    matched = defaultdict(dict)
    for r in rows:
        if not all(k in r for k in
                   ("active_filter_gates","matched_50pct_return_pct",
                    "matched_50pct_mdd_pct","matched_50pct_trades")):
            raise ValueError("MISSING_MATCHED_ALLOCATION_FIELDS")
        if r["matched_50pct_trades"] != r["trades"]:
            raise ValueError("MATCHED_SIZE_CHANGED_POSITION_COUNT")
        key = (r["policy_id"], r["model"])
        if r["year"] in matched[key]:
            raise ValueError("DUPLICATE_MATCHED_YEAR")
        matched[key][r["year"]] = r
    tiers = defaultdict(list)
    for result in main["rows"]:
        key = (result["policy_id"], result["model"])
        group = matched[key]
        if set(group) != {2025, 2026}:
            raise ValueError("MISSING_PAIRED_MATCHED_RESULTS")
        a, b = group[2025], group[2026]
        if a["active_filter_gates"] != b["active_filter_gates"]:
            raise ValueError("INCONSISTENT_FILTER_BUDGET")
        result.update({
            "active_filter_gates": a["active_filter_gates"],
            "matched_50pct_return_2025_pct": a["matched_50pct_return_pct"],
            "matched_50pct_return_2026_ytd_pct": b["matched_50pct_return_pct"],
            "matched_50pct_mdd_2025_pct": a["matched_50pct_mdd_pct"],
            "matched_50pct_mdd_2026_ytd_pct": b["matched_50pct_mdd_pct"],
            "matched_50pct_worst_year_return_pct":
                min(a["matched_50pct_return_pct"], b["matched_50pct_return_pct"]),
            "matched_50pct_both_years_positive":
                a["matched_50pct_return_pct"] > 0 and b["matched_50pct_return_pct"] > 0,
        })
        if result["config_index"] > 0: # baseline excluded from distribution
            tiers[(result["model"], result["active_filter_gates"])].append(result)
    budget_summary = {}
    for model in ("price_only", "integrated_regime"):
        out = {}
        for tier in range(5):
            group = tiers[(model, tier)]
            if len(group) != (expected_configs - 1) // 5:
                raise ValueError(f"NOT_BALANCED_FILTER_BUDGET_{model}_{tier}:{len(group)}")
            n = len(group)
            eligible = [r for r in group if r["qualified_min_15_trades_each_year"]]
            active = [r for r in group if min(r["trades_2025"], r["trades_2026_ytd"]) > 0]
            out[str(tier)] = {
                "candidate_configs": n,
                "both_years_nonzero_trades": len(active),
                "at_least_15_trades_per_year": len(eligible),
                "qualified_both_years_native_positive":
                    sum(r["both_years_positive"] for r in eligible),
                "qualified_both_years_matched50_positive":
                    sum(r["matched_50pct_both_years_positive"] for r in eligible),
                "median_min_year_trades": float(np.median(
                    [min(r["trades_2025"],r["trades_2026_ytd"]) for r in group])),
                "matched_50pct_median_worst_year_return_for_qualified_pct":
                    round(float(np.median([r["matched_50pct_worst_year_return_pct"] for r in eligible])), 5)
                    if eligible else None,
            }
        budget_summary[model] = out
    matched_leaders = {}
    for model in ("price_only", "integrated_regime"):
        rows_model = [r for r in main["rows"]
                      if r["model"] == model and r["qualified_min_15_trades_each_year"]]
        # Low trades are not allowed to lead; 0-trade policies remain in full report.
        matched_leaders[model] = sorted(
            rows_model,
            key=lambda r: (r["matched_50pct_worst_year_return_pct"],
                           -min(r["matched_50pct_mdd_2025_pct"],
                                r["matched_50pct_mdd_2026_ytd_pct"])),
            reverse=True)[:20]
    main.update({
        "schema": "qld-40axis-10000-structured-and-size-matched-v1",
        "status": "EXPLORATORY_NOT_INDEPENDENT_POLICY_OOS",
        "sampling": items[0]["generator"],
        "comparison": "NATIVE_POLICY + FIXED_50PCT_CASH_ALLOCATION_WITH_NO_OTHER_PARAMS_CHANGED",
        "matched_allocation_caveat": "Fixed nominal size 50% is not equal stop-loss risk across policies; do not rescale returns as if leverage or fill conditions were unchanged.",
        "filter_budget_stats_excluding_baseline": budget_summary,
        "matched50_rankings_qualified_only": matched_leaders,
        "full_trade_models_by_year": len(rows),
        "hold_live": True,
    })
    return main


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--configs", type=int, default=10001)
    p.add_argument("--out", required=True)
    a=p.parse_args()
    result=summarize_structured(sorted(Path(a.source).rglob("joint_shard_*.json")), a.configs)
    output=Path(a.out)
    output.mkdir(parents=True, exist_ok=True)
    (output/"structured_all_results.json").write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
    summary={k:v for k,v in result.items() if k!="rows"}
    (output/"structured_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print("STRUCTURED40_AGGREGATE "+json.dumps({
        "status":result["status"],
        "total_configs":result["configs_evaluated"],
        "total_portfolios":result["full_trade_models_by_year"],
        "budget_stats":result["filter_budget_stats_excluding_baseline"],
        "top3_common_cash":{model:[{
            "policy_id":a["policy_id"],
            "active_filter_gates":a["active_filter_gates"],
            "trades_2025":a["trades_2025"],
            "trades_2026":a["trades_2026_ytd"],
            "matched_return_2025":a["matched_50pct_return_2025_pct"],
            "matched_return_2026":a["matched_50pct_return_2026_ytd_pct"],
            "native_return_2025":a["return_2025_pct"],
            "native_return_2026":a["return_2026_ytd_pct"],
        } for a in arr[:3]] for model,arr in result["matched50_rankings_qualified_only"].items()},
        "live_unchanged":True,
    },ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
