#!/usr/bin/env python3
"""Strict read-only 1:1 existing Opportunity/Quote native-parent verification.

Consumes the 177 structural candidates (and previously verified Contact->Oppo
evidence) from the authorized workstation. Traverses the exact Opportunity
Related Quotation list and then Quote Details native parent field.
Never clicks Save or creates Product, Quote, or Opportunity.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from verify_related_quote_native_parent import run_live,same_native
ROOT=Path.home()/".sfdc_desktop"
SOURCE="one_to_one_oppo_quote_learning_shortlist_PRIVATE.json"
OUTPUT="one_to_one_quote_native_parent_verified_PRIVATE.json"
ORDER=("Need to submit","Ready to send")


def choose_verified_contact_cases(candidates,per_status=2):
    if not isinstance(candidates,list) or type(per_status) is not int or not 1<=per_status<=5:
        raise ValueError("INVALID_CANDIDATE_SCOPE")
    used=Counter()
    result=[]
    for status in ORDER:
        for item in candidates:
            if used[status]>=per_status:
                break
            if (isinstance(item,dict) and item.get("quote_status")==status
                    and item.get("known_contact_opportunity_live_evidence") is True
                    and item.get("native_quote_parent_independently_live_verified") is False
                    and item.get("salesforce_save_allowed") is False):
                used[status]+=1
                result.append(item)
    return result


def classify_native_parent(candidate,actual):
    if not isinstance(candidate,dict) or not isinstance(actual,dict):
        return "HOLD_INVALID_NATIVE_EVIDENCE"
    if (actual.get("parent_verified") is not True or
            actual.get("quote_id_verified") is not True):
        return "HOLD_"+str(actual.get("status") or "UNVERIFIED")
    if not same_native(candidate.get("opportunity_id"),actual.get("opportunity_id_private")):
        return "HOLD_OPPO_ID_CONFLICT"
    if not same_native(candidate.get("quote_id"),actual.get("quotation_id_private")):
        return "HOLD_QUOTE_ID_CONFLICT"
    return "PASS_NATIVE_QUOTE_AND_PARENT_IDS"


def select_remaining_native_cases(candidates,prior,*,all_structural=False,limit=25):
    """Select existing one-to-one pairs never attempted, with no CRM write gate.

    An identity-verified native parent is independent from Contact proof. A
    structural-only case must continue to require Contact verification for use
    in any subsequent preparation workflow.
    """
    if not isinstance(candidates,list) or not isinstance(prior,list):
        raise ValueError("INVALID_CANDIDATE_OR_HISTORY")
    if type(limit) is not int or not 1<=limit<=50:
        raise ValueError("INVALID_READBACK_BATCH_LIMIT")
    attempted=set()
    for row in prior:
        if isinstance(row,dict):
            key=(row.get("opportunity_id"),row.get("quote_id"))
            attempted.add(key)
    selected=[]
    seen=set()
    for row in candidates:
        if not isinstance(row,dict):
            continue
        key=(row.get("opportunity_id"),row.get("quote_id"))
        if key in attempted or key in seen or row.get("salesforce_save_allowed") is not False:
            continue
        if row.get("native_quote_parent_independently_live_verified") is not False:
            continue
        if not all_structural and row.get("known_contact_opportunity_live_evidence") is not True:
            continue
        selected.append(row)
        seen.add(key)
        if len(selected)>=limit:
            break
    return selected


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--per-status",type=int,default=2)
    p.add_argument("--all-contact-verified",action="store_true")
    p.add_argument("--all-structural",action="store_true",
                   help="Read-only native parent check even if Contact still unverified")
    p.add_argument("--max-cases",type=int,default=25)
    args=p.parse_args()
    if args.all_structural and args.all_contact_verified:
        raise SystemExit("HOLD_MUTUALLY_EXCLUSIVE_SELECTION")
    candidates=json.loads((ROOT/SOURCE).read_text(encoding="utf-8-sig"))["candidates"]
    existing_path=ROOT/OUTPUT
    previous=json.loads(existing_path.read_text(encoding="utf-8-sig")) if existing_path.exists() else []
    if not isinstance(previous,list):
        raise SystemExit("HOLD_PREVIOUS_NATIVE_PARENT_REPORT_INVALID")
    approved={(r.get("opportunity_id"),r.get("quote_id")) for r in previous
              if isinstance(r,dict) and r.get("native_relation_status")=="PASS_NATIVE_QUOTE_AND_PARENT_IDS"}
    if args.all_contact_verified or args.all_structural:
        cases=select_remaining_native_cases(
            candidates,previous,all_structural=args.all_structural,limit=args.max_cases)
    else:
        cases=[r for r in choose_verified_contact_cases(candidates,args.per_status)
               if (r.get("opportunity_id"),r.get("quote_id")) not in approved]
    rows=list(previous)
    newly_checked=0
    for index,item in enumerate(cases,1):
        try:
            live=run_live(item["opportunity_id"])
            status=classify_native_parent(item,live)
        except Exception as exc:
            status="HOLD_"+type(exc).__name__
        newly_checked+=1
        rows.append({
            "opportunity_id":item["opportunity_id"],
            "quote_id":item["quote_id"],
            "quote_status":item["quote_status"],
            "contact_opportunity_verified_in_source":item.get("known_contact_opportunity_live_evidence") is True,
            "native_relation_status":status,
            "save_clicked":False
        })
        (ROOT/OUTPUT).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
        print("ONE_TO_ONE_NATIVE_ID_CHECK",index,"/",len(cases),status,flush=True)
    counts=Counter(x["native_relation_status"] for x in rows)
    print("ONE_TO_ONE_NATIVE_SUMMARY",json.dumps({
        "checked":len(rows),"newly_checked":newly_checked,
        "native_verified":counts["PASS_NATIVE_QUOTE_AND_PARENT_IDS"],
        "hold":len(rows)-counts["PASS_NATIVE_QUOTE_AND_PARENT_IDS"],
        "new_quote_save_allowed":False,"salesforce_writes":0,
    },sort_keys=True))


if __name__=="__main__":
    main()
