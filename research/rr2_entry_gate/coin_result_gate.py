#!/usr/bin/env python3
"""Read-only promotion gate on immutable aggregated COIN structural RR2 results."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS=("ORL_BUFFER_2R","PRIOR_LOW_BUFFER_2R","FIXED_2PCT_2R","ORL_PRIOR20_HIGH")
HOLDS=(1,2,4)
EXPECTED_CELLS={(year,arm,hold) for year in (2024,2025,2026)
                for arm in ARMS for hold in HOLDS}

def review(path,expected_sha=None):
    raw=path.read_bytes()
    source_hash=hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and source_hash!=expected_sha:
        raise ValueError("SOURCE_SHA_MISMATCH")
    d=json.loads(raw)
    if d.get("schema")!="coin-structure-rr2-all-sessions-pilot-v1":
        raise ValueError("SCHEMA_MISMATCH")
    if d.get("status")!="RESEARCH_ONLY_NOT_MODEL_SIGNAL_MATCHED" or d.get("live")!="HOLD":
        raise ValueError("UNSAFE_LIVE_STATE")
    if (d.get("min_net_rr"),d.get("roundtrip_cost_fraction"),
        d.get("max_stop_fraction"),d.get("max_target_fraction")) != (2.0,.003,.03,.08):
        raise ValueError("POLICY_DRIFT")
    if d.get("signal_cohort")!="ALL_COMPLETE_EXCHANGE_SESSIONS_NOT_V_UNWEIGHTED_SIGNALS":
        raise ValueError("MATCHED_SIGNAL_FALSE_CLAIM")
    quality=d["quality"]
    if (quality.get("expected_sessions"),quality.get("complete_sessions"),
        quality.get("incomplete_sessions"))!=(711,711,0):
        raise ValueError("SIP_COVERAGE_DRIFT")
    results=d["results"]
    indexed={}
    for row in results:
        key=(row["year"],row["arm"],row["hold_sessions"])
        if key in indexed or key not in EXPECTED_CELLS: raise ValueError("UNEXPECTED_OR_DUPLICATE_ARM")
        if not (isinstance(row.get("trades"),int)
                and isinstance(row.get("geometry_pass"),int)
                and 0<=row["trades"]<=row["geometry_pass"]<=row["all_sessions_after_warmup"]):
            raise ValueError("INVALID_COUNTS")
        if row["trades"]:
            for k in ("mean_R","mean_net_pct","total_return_pct","eod_mdd_pct"):
                if not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]):
                    raise ValueError("NONFINITE_RESULT")
            if row["eod_mdd_pct"]>0: raise ValueError("BAD_DRAWDOWN")
        indexed[key]=row
    if set(indexed)!=EXPECTED_CELLS: raise ValueError("MISSING_CELLS")
    # Ex-ante: pick 2024 only, then report 2025 and 2026 without tuning.
    baseline=[indexed[(2024,a,h)] for a in ARMS for h in HOLDS
              if indexed[(2024,a,h)]["trades"]>=20]
    if not baseline:raise ValueError("NO_2024_TRAIN_ARM")
    chosen=sorted(baseline,key=lambda r:(-r["mean_R"],r["hold_sessions"],r["arm"]))[0]
    key=(chosen["arm"],chosen["hold_sessions"])
    validation=[indexed[(y,*key)] for y in (2025,2026)]
    stability=[{
        "arm":arm,"hold_sessions":h,
        "2025_mean_R":indexed[(2025,arm,h)]["mean_R"],
        "2026_mean_R":indexed[(2026,arm,h)]["mean_R"],
        "both_positive":all(indexed[(y,arm,h)]["mean_R"]>0 for y in (2025,2026)),
        "min_year_trades":min(indexed[(y,arm,h)]["trades"] for y in (2025,2026))
    } for arm in ARMS for h in HOLDS]
    cross_year_positive=sum(x["both_positive"] for x in stability)
    selected_both_positive=all(x["mean_R"]>0 for x in validation)
    # Explicitly require future genuine OOS and model signal matched replay, absent here.
    return {
        "schema":"coin-structural-rr2-selection-audit-v1",
        "status":"REVIEWED_LIVE_HOLD",
        "source_sha256":source_hash,
        "eligible_for_live":False,
        "reasons":["UNCONDITIONAL_SESSIONS_NOT_SIGNAL_MATCHED",
                   "NO_NEW_UNSEEN_OOS","NO_2025_2026_STABLE_POSITIVE_R"],
        "sessions":quality["complete_sessions"],
        "year_2026_partial_through":"2026-10-30",
        "distinct_designs":len(ARMS),"horizons":HOLDS,
        "both_positive_2025_2026":cross_year_positive,
        "arms_compared":len(stability),
        "2024_selection":{"arm":key[0],"hold_sessions":key[1],
                          "mean_R":chosen["mean_R"],"trades":chosen["trades"]},
        "out_of_sample_years_reused_from_research":True,
        "validation":[{"year":r["year"],"mean_R":r["mean_R"],"trades":r["trades"],
                       "eod_mdd_pct":r["eod_mdd_pct"]} for r in validation],
        "selected_both_positive":selected_both_positive,
        "stability":stability
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--summary",required=True,type=Path)
    p.add_argument("--expected-sha256")
    p.add_argument("--out",type=Path,default=Path("outputs/coin_rr2_review/review.json"))
    args=p.parse_args()
    result=review(args.summary,args.expected_sha256)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in
        ("status","eligible_for_live","sessions","both_positive_2025_2026",
         "2024_selection","validation")},ensure_ascii=False))
if __name__=="__main__":main()
