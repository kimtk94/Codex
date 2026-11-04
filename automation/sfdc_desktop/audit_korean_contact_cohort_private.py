#!/usr/bin/env python3
"""Private, deterministic cohort audit without leaking CRM records.

The first ten records predate the append-only attempt ledger. Non-PASS records
in that historical cohort are marked legacy HOLD, not newly tested today.
"""
import json
from collections import Counter
from pathlib import Path
import live_contact_alias_batch_private as study
from build_private_contact_aliases import verified_private_aliases

ROOT=Path.home()/".sfdc_desktop"


def summarize_cohort(candidates, verified, attempts, legacy_first=10):
    if not isinstance(candidates,list) or not isinstance(verified,list) or not isinstance(attempts,list):
        raise ValueError("INVALID_COHORT")
    if not 0<=legacy_first<=len(candidates):
        raise ValueError("INVALID_LEGACY_SIZE")
    verified_ids={x.get("contact_id") for x in verified if isinstance(x,dict)}
    attempts_by_id={}
    for row in attempts:
        if isinstance(row,dict) and isinstance(row.get("contact_id"),str):
            attempts_by_id[row["contact_id"]]=row.get("status") or "HOLD_UNKNOWN"
    statuses=[]
    ids_seen=set()
    for index,row in enumerate(candidates):
        identifier=row.get("contact_id")
        if identifier in ids_seen:
            raise ValueError("DUPLICATE_COHORT_CONTACT_ID")
        ids_seen.add(identifier)
        if identifier in verified_ids:
            status="VERIFIED"
        elif identifier in attempts_by_id:
            status="HOLD"
        elif index<legacy_first:
            status="HOLD_LEGACY_NO_ATTEMPT_LEDGER"
        else:
            status="UNTESTED"
        statuses.append(status)
    counts=Counter(statuses)
    return {"cohort_count":len(candidates),"verified":counts["VERIFIED"],
            "hold":counts["HOLD"]+counts["HOLD_LEGACY_NO_ATTEMPT_LEDGER"],
            "hold_legacy":counts["HOLD_LEGACY_NO_ATTEMPT_LEDGER"],
            "untested":counts["UNTESTED"],
            "audited_total":counts["VERIFIED"]+counts["HOLD"]+counts["HOLD_LEGACY_NO_ATTEMPT_LEDGER"],
            "verified_outside_cohort":len(verified_ids-ids_seen),
            "save_allowed":False}


def main():
    source=study.candidates()
    evidence_path=ROOT/"private_verified_contact_details_evidence.json"
    attempts_path=ROOT/"contact_alias_attempts_PRIVATE.json"
    evidence=json.loads(evidence_path.read_text(encoding="utf-8-sig")) if evidence_path.exists() else []
    attempts=json.loads(attempts_path.read_text(encoding="utf-8-sig")) if attempts_path.exists() else []
    report=summarize_cohort(source,evidence,attempts)
    aliases=verified_private_aliases(evidence)
    report["web_aliases_accepted"]=len(aliases["records"])
    report["alias_conflicts"]=aliases["conflicting_identity_keys"]
    report["scope"]="HISTORICAL_180_OPPORTUNITY_SUBCOHORT"
    report["web_live_salesforce_search_ready"]=False
    output=ROOT/"contact_alias_cohort_summary_PRIVATE.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("CONTACT_COHORT_SUMMARY",json.dumps(report,sort_keys=True))
    if report["verified"]!=report["web_aliases_accepted"]:
        raise SystemExit("HOLD_PRIVATE_ALIAS_COUNT_MISMATCH")


if __name__=="__main__":
    main()
