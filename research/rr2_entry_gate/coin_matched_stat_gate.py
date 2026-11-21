#!/usr/bin/env python3
"""Fail-closed statistical audit of matched COIN R>=2 research aggregates.

No hidden per-trade prices, licensed candles or signal dates are accepted or
published. Binomial Wilson intervals are for target-hit frequency ONLY, not
intervals for average realized R or a proof of positive expectancy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

ORIGIN = "cccbb80059ab626da0cbd76cd825f879870f6727"
SYMBOLS = ("COIN", "IWM", "MU", "SMH", "SPY")
ARMS = ("ORL_BUFFER_2R", "PRIOR_LOW_BUFFER_2R", "FIXED_2PCT_2R", "ORL_PRIOR20_HIGH")
HOLDS = (1, 2, 4)
YEARS = (2025, 2026)
Z_95 = 1.959963984540054


def wilson_lower(k: int, n: int, z=Z_95) -> float | None:
    if not isinstance(k, int) or not isinstance(n, int) or n < 0 or not 0 <= k <= n:
        raise ValueError("INVALID_BINOMIAL_COUNTS")
    if n == 0:
        return None
    p = k / n
    a = z*z
    return (p+a/(2*n)-z*math.sqrt(p*(1-p)/n+a/(4*n*n)))/(1+a/n)


def audit(path: Path, expected_sha256: str | None = None):
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and sha != expected_sha256:
        raise ValueError("ORIGINAL_MATCHED_AGGREGATE_SHA_DRIFT")
    j = json.loads(raw)
    if j.get("schema") != "coin-rr2-v-unweighted-pit-signal-replay-v1":
        raise ValueError("WRONG_REPLAY_SCHEMA")
    if j.get("status") != "MATCHED_LEDGER_RESEARCH_ONLY_NOT_UNSEEN_OOS":
        raise ValueError("NO_MATCHED_REPLAY")
    if (j.get("live") != "HOLD" or j.get("not_fresh_oos") is not True
            or j.get("no_broker_or_live_change") is not True):
        raise ValueError("FORBIDDEN_LIVE_PROMOTION")
    if {int(k):v for k,v in j["signals_verified"].items()} != {2025:80,2026:46}:
        raise ValueError("COIN_126_SIGNAL_DRIFT")
    provenance = j["provenance"]
    if (provenance.get("original_commit") != ORIGIN
            or provenance.get("original_success_run") != 41217666574
            or provenance.get("original_bar_count") != 221014
            or provenance.get("can_promote_live") is not False
            or provenance.get("type") != "RECONSTRUCTED_SOURCE_NOT_ORIGINAL_SAVED_SIGNAL_LEDGER"):
        raise ValueError("SOURCE_LINEAGE_DRIFT")
    counts = provenance["full_universe_signal_count_parity"]
    eod = provenance["full_universe_EOD_return_parity"]
    if set(counts) != set(SYMBOLS) or set(eod) != set(SYMBOLS):
        raise ValueError("FIVE_SYMBOL_PARITY_MISSING")
    for sym in SYMBOLS:
        for y in YEARS:
            row = counts[sym][str(y)]
            if set(row) != {"P_unweighted","V_unweighted"}:
                raise ValueError("MODEL_COUNT_PARITY_MISSING")
            if not eod[sym][str(y)]["within_1e_5_percentage_points"]:
                raise ValueError("ORIGINAL_NET_RETURN_MISMATCH")
    if j["quality"]["incomplete_sessions"] != 0 or j["quality"]["complete_sessions"] != 711:
        raise ValueError("SIP_COVERAGE_DRIFT")
    if any(j["baseline_parity"][str(y)]["original_atr125_stop300_gate_pass"] != 0 for y in YEARS):
        raise ValueError("ORIGINAL_NET_RR_BASELINE_CHANGED")
    indexed = {}
    for r in j["results"]:
        key = (r["year"],r["arm"],r["hold_sessions"])
        if key in indexed or key not in {(y,a,h) for y in YEARS for a in ARMS for h in HOLDS}:
            raise ValueError("UNEXPECTED_OR_DUPLICATE_CELL")
        n = r["trades"]
        candidate = r["original_signals"]
        valid = r["structural_pass"]
        reject = sum(r["first_rejection_counts"].values())
        if (not all(isinstance(v,int) for v in (n,candidate,valid,reject))
                or not 0 <= n <= valid <= candidate
                or candidate != {2025:80,2026:46}[r["year"]]
                or valid+reject != candidate
                or valid-r["overlap_blocked"]-r["right_censored"] != n):
            raise ValueError("COHORT_ACCOUNTING_MISMATCH")
        if n != r["stop_count"] + r["target_count"] + r["time_count"]:
            raise ValueError("EXIT_TOTAL_MISMATCH")
        if r["stop_gap_count"] > r["stop_count"]:
            raise ValueError("INVALID_GAP_COUNT")
        if n and (r["mean_R"] is None or not math.isfinite(r["mean_R"])
                  or r["eod_mdd_pct"] > 0):
            raise ValueError("INVALID_RETURN_OR_DRAWDOWN")
        for stress in ("50bp","100bp"):
            nr = r[f"cost_stress_{stress}_planned_rr2_count"]
            if not isinstance(nr,int) or not 0 <= nr <= n:
                raise ValueError("INVALID_STRESSED_RR2_ELIGIBILITY")
        indexed[key] = r
    if len(indexed)!=24:
        raise ValueError("INCOMPLETE_24_RESEARCH_CELLS")

    details=[]
    for a in ARMS:
        for h in HOLDS:
            pair = [indexed[(y,a,h)] for y in YEARS]
            summaries = []
            for y,r in zip(YEARS,pair):
                n,targets=r["trades"],r["target_count"]
                lb=wilson_lower(targets,n)
                summaries.append({
                    "year":y,"trades":n,"mean_R":r["mean_R"],
                    "geometry_pass":r["structural_pass"],
                    "targets":targets,"stops_including_gap":r["stop_count"],
                    "stop_gap":r["stop_gap_count"],
                    "target_hit_rate":round(targets/n,6) if n else None,
                    "wilson95_lower_target_hit":round(lb,6) if lb is not None else None,
                    "roundtrip_50bp_RR2_eligible":r["cost_stress_50bp_planned_rr2_count"],
                    "roundtrip_100bp_RR2_eligible":r["cost_stress_100bp_planned_rr2_count"],
                    "cost_50bp_mean_R_but_not_validated_geometry":r["cost_stress_50bp_mean_R"],
                })
            details.append({
                "arm":a,"hold_sessions":h,
                "both_years_mean_R_positive":all(r["trades"] and r["mean_R"]>0 for r in pair),
                "both_years_at_least_30_trades":all(r["trades"]>=30 for r in pair),
                "years":summaries,
                "go":False
            })
    b=next(d for d in details if d["arm"]=="PRIOR_LOW_BUFFER_2R" and d["hold_sessions"]==4)
    return {
        "schema":"coin-original-model-signal-statistical-gate-v1",
        "status":"SOURCE_PARITY_PASS_STATISTICAL_STABILITY_HOLD",
        "source_sha256":sha,
        "live":"HOLD","eligible_for_live":False,
        "reused_research_years_not_fresh_oos":True,
        "original_signal_model_match":True,
        "independent_historical_saved_ledger_verified":False,
        "replication_source":"PINNED_ORIGINAL_MODEL_RECOMPUTATION",
        "tested_configurations":len(details),
        "configurations_positive_in_both_years":sum(d["both_years_mean_R_positive"] for d in details),
        "configurations_with_30_trades_both_years":sum(d["both_years_at_least_30_trades"] for d in details),
        "not_adjusted_for_12_correlated_configs":True,
        "wilson_interval_scope":"TARGET_HIT_FREQUENCY_ONLY_NOT_EXPECTED_R_CI",
        "individual_trade_returns_not_published":True,
        "B_prior_low_4sessions":b,
        "strategies":details,
        "promotion_blockers":[
            "NO_PREVIOUSLY_UNSEEN_OOS",
            "NO_BOTH_YEAR_POSITIVE_EXPECTANCY",
            "SAMPLE_SIZE_UNSTABLE_FOR_SELECTED_2026_B",
            "COST_STRESS_RR2_TARGET_REPRICING_REQUIRED",
            "NO_SPREAD_QUOTE_LATENCY_FILL_VALIDATION",
            "WILSON_TARGET_RATE_IS_NOT_RETURN_CONFIDENCE_INTERVAL",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--matched-aggregate",type=Path,required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    report=audit(a.matched_aggregate,a.expected_sha256)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({
        "status":report["status"],
        "both_positive":report["configurations_positive_in_both_years"],
        "tested":report["tested_configurations"],
        "2026_B_n":report["B_prior_low_4sessions"]["years"][1]["trades"],
        "2026_B_wilson_target_lower95":report["B_prior_low_4sessions"]["years"][1]["wilson95_lower_target_hit"],
        "eligible_for_live":False
    }))

if __name__=="__main__":
    main()
