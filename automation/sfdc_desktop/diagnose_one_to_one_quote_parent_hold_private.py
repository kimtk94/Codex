#!/usr/bin/env python3
"""Three independent, read-only reruns of exceptional existing Quote parent.

Never auto-promotes an existing HOLD. Confirms whether a 1:1 Related-list
failure was a transient screen issue, a stable non-1:1 count, or an ID
conflict. Outputs only aggregate codes; native IDs stay on authorized PC.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from verify_related_quote_native_parent import run_live
from verify_one_to_one_quote_native_parents_private import classify_native_parent

ROOT=Path.home()/".sfdc_desktop"
SOURCE="one_to_one_quote_native_parent_verified_PRIVATE.json"
OUT="one_to_one_quote_hold_three_readback_PRIVATE.json"


def classify_three_passes(expected,results):
    if not isinstance(results,list) or len(results)!=3:
        return "HOLD_NOT_THREE_INDEPENDENT_READBACKS"
    statuses=[classify_native_parent(expected,r) for r in results]
    if all(s=="PASS_NATIVE_QUOTE_AND_PARENT_IDS" for s in statuses):
        return "REVIEW_RECOVERED_3_OF_3_NO_AUTO_PROMOTION"
    counts={r.get("observed_related_quote_count") for r in results
            if isinstance(r,dict)}
    if len(counts)==1 and next(iter(counts)) not in (None,1):
        return "HOLD_RELATED_COUNT_STABLE_NOT_ONE"
    if any(s in ("HOLD_QUOTE_ID_CONFLICT","HOLD_OPPO_ID_CONFLICT") for s in statuses):
        return "HOLD_NATIVE_ID_CONFLICT"
    return "HOLD_INCONSISTENT_OR_INCOMPLETE_READBACK"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=1)
    args=p.parse_args()
    if not 1<=args.limit<=3:raise SystemExit("HOLD_BATCH_SIZE_LIMIT")
    saved=json.loads((ROOT/SOURCE).read_text(encoding="utf-8-sig"))
    if not isinstance(saved,list):raise SystemExit("HOLD_INVALID_PARENT_HISTORY")
    cases=[]
    visited=set()
    for row in saved:
        if not isinstance(row,dict) or not str(row.get("native_relation_status","")).startswith("HOLD_"):
            continue
        key=(row.get("opportunity_id"),row.get("quote_id"))
        if key in visited:continue
        visited.add(key)
        cases.append(row)
        if len(cases)>=args.limit:break
    records=[]
    for case in cases:
        results=[]
        for cycle in range(1,4):
            try:
                r=run_live(case["opportunity_id"])
            except Exception as exc:
                r={"status":"HOLD_"+type(exc).__name__}
            results.append(r)
            print("PARENT_HOLD_DIAGNOSTIC_READ",cycle,"STATUS",r.get("status"),
                  "RELATED_COUNT",r.get("observed_related_quote_count"),flush=True)
        review=classify_three_passes(case,results)
        records.append({
            "opportunity_id":case["opportunity_id"],
            "quote_id":case["quote_id"],
            "original_hold_status":case["native_relation_status"],
            "review":review,
            "statuses":[r.get("status") for r in results],
            "related_counts":[r.get("observed_related_quote_count") for r in results],
            "save_clicked":False,
        })
        (ROOT/OUT).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
        print("PARENT_HOLD_DIAGNOSTIC",review,flush=True)
    print("PARENT_HOLD_DIAGNOSTIC_SUMMARY",json.dumps({
        "cases":len(records),"result_types":dict(Counter(r["review"] for r in records)),
        "native_parent_report_unchanged":True,"salesforce_writes":0
    },sort_keys=True))


if __name__=="__main__":
    main()
