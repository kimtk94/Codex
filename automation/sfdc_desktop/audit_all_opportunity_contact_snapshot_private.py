#!/usr/bin/env python3
"""Aggregate full in-scope Opportunity->Contact reconciliation, read-only.

The 1,013 Opportunity list supplies *name-based* candidates. Only independent
authenticated Contact, Account and Opportunity field checks in a private
workstation evidence file count as verified. Never publish customer identities.
"""
import json
from collections import Counter
from pathlib import Path

from contact_oppo_selection import ID_CONTACT,ID_OPPORTUNITY,excluded_account
from build_private_contact_aliases import verified_private_aliases

ROOT=Path.home()/".sfdc_desktop"
OPPS="oppo_linked_contact_candidate_manifest_PRIVATE.json"
APPROVED="private_verified_contact_details_evidence.json"
OUTPUT="all_opportunity_contact_reconciliation_PRIVATE.json"
FLAGS=(
 "contact_detail_id_verified",
 "contact_account_link_verified",
 "opportunity_contact_link_verified",
 "contact_email_verified",
 "contact_display_name_verified",
)


def summarize_opportunities(opportunities,evidence):
    if not isinstance(opportunities,list) or not isinstance(evidence,list):
        raise ValueError("INVALID_PRIVATE_SOURCE")
    rows={}
    statuses=Counter()
    match_lengths=Counter()
    for row in opportunities:
        if not isinstance(row,dict):
            raise ValueError("INVALID_OPPORTUNITY_ROW")
        oid=row.get("opportunity_id")
        if not isinstance(oid,str) or not ID_OPPORTUNITY.fullmatch(oid) or oid in rows:
            raise ValueError("INVALID_OR_DUPLICATE_OPPORTUNITY")
        if excluded_account(row.get("institution_hint")):
            raise ValueError("EXCLUDED_INSTITUTION_IN_SCOPE_MANIFEST")
        candidates=row.get("candidate_contact_ids")
        if not isinstance(candidates,list) or not all(
            isinstance(cid,str) and ID_CONTACT.fullmatch(cid) for cid in candidates
        ):
            raise ValueError("INVALID_CANDIDATE_CONTACT_IDS")
        rows[oid]=row
        statuses[row.get("status") or "UNKNOWN"]+=1
        match_lengths[len(candidates)]+=1
    verified_contacts=verified_private_aliases(evidence)
    approved_unique={r["contact_id"] for r in verified_contacts["records"]}
    seen_opps=set()
    verified_in_inventory=0
    approved_opp_mismatch=0
    approved_opp_not_found=0
    approved_not_all_flags=0
    for record in evidence:
        if not isinstance(record,dict):
            continue
        if not all(record.get(k) is True for k in FLAGS):
            approved_not_all_flags+=1
            continue
        cid=record.get("contact_id")
        oid=record.get("opportunity_id")
        if cid not in approved_unique or not isinstance(oid,str) or not ID_OPPORTUNITY.fullmatch(oid):
            continue
        if oid in seen_opps:
            continue
        seen_opps.add(oid)
        if oid not in rows:
            approved_opp_not_found+=1
        elif cid not in rows[oid]["candidate_contact_ids"]:
            approved_opp_mismatch+=1
        else:
            verified_in_inventory+=1
    return {
        "scope":"IN_SCOPE_OPPORTUNITY_SNAPSHOT_NOT_FULL_LIVE_RECHECK",
        "opportunity_inventory_count":len(rows),
        "name_candidate_status_counts":dict(sorted(statuses.items())),
        "candidate_id_multiplicity":dict(sorted(match_lengths.items())),
        "approved_unique_native_contacts":len(approved_unique),
        "approved_native_opportunity_ids_in_manifest":verified_in_inventory,
        "independently_approved_opportunity_id_candidate_conflicts":approved_opp_mismatch,
        "approved_opportunity_id_not_in_manifest":approved_opp_not_found,
        "evidence_rows_missing_full_identity_flags":approved_not_all_flags,
        "unapproved_opportunity_rows":len(rows)-verified_in_inventory,
        "all_opportunities_have_native_verified_contact":False,
        "salesforce_save_allowed":False,
        "salesforce_writes":0,
    }


def main():
    source=json.loads((ROOT/OPPS).read_text(encoding="utf-8-sig"))
    evidence=json.loads((ROOT/APPROVED).read_text(encoding="utf-8-sig"))
    output=summarize_opportunities(source,evidence)
    (ROOT/OUTPUT).write_text(json.dumps(output,indent=2,sort_keys=True),encoding="utf-8")
    print("ALL_SFDC_OPPORTUNITY_CONTACT_AUDIT",json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
