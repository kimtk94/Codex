#!/usr/bin/env python3
"""Conservative 1:1 Oppo–Quote learning shortlist from *all* quote inventory.

The shortlist is a structural hint only. Historical list names and manifest
parent IDs are NOT a substitute for independently opening the native Quote
parent field in authenticated Salesforce. No Salesforce writes or price reuse.
All IDs/customer details remain on the authorized private workstation.
"""
import json
from collections import Counter
from pathlib import Path

from audit_complete_sfdc_oppo_quote_snapshot_private import summary
from contact_oppo_selection import excluded_account
from build_private_contact_aliases import verified_private_aliases

ROOT=Path.home()/".sfdc_desktop"
FULL="all_quotation_inventory_20261103_PRIVATE.json"
ONE="oppo_quote_single_product_learning_manifest_PRIVATE.json"
OPPS="oppo_linked_contact_candidate_manifest_PRIVATE.json"
EVIDENCE="private_verified_contact_details_evidence.json"
OUTPUT="one_to_one_oppo_quote_learning_shortlist_PRIVATE.json"


def one_to_one_candidates(full,one,opps,evidence):
    audited=summary(full,one,opps)  # validates full 862 snapshot and column map
    by_opp={row["opportunity_id"]:row for row in opps}
    opp_name_count=Counter(row["opportunity_name"] for row in opps)
    quote_opp_name_count=Counter(row["cells"][4] for row in full["rows"])
    approved_ids={oid for row in evidence if isinstance(row,dict)
                  and all(row.get(k) is True for k in (
                      "contact_detail_id_verified","contact_account_link_verified",
                      "opportunity_contact_link_verified","contact_email_verified",
                      "contact_display_name_verified"))
                  for oid in row.get("opportunity_ids",[])
                  if isinstance(oid,str)}
    candidates=[]
    for row in one:
        oid=row["oppo_id"]
        opp=by_opp.get(oid)
        if not opp or excluded_account(opp.get("institution_hint")):
            continue
        name=row.get("oppo_name")
        if not isinstance(name,str) or not name:
            continue
        if (name!=opp.get("opportunity_name")
                or row.get("contact_display")!=opp.get("contact_display")
                or not isinstance(row.get("quote_name"),str)
                or not row["quote_name"].startswith(name+"-")
                or str(row.get("product_records"))!="1"
                or opp_name_count[name]!=1 or quote_opp_name_count[name]!=1):
            continue
        candidates.append({
            "quote_id":row["quote_id"],
            "opportunity_id":oid,
            "quote_status":row.get("quote_status"),
            "single_product_snapshot":True,
            "snapshot_opportunity_and_contact_labels_match":True,
            "quote_name_unique_in_full_inventory":True,
            "known_contact_opportunity_live_evidence":oid in approved_ids,
            "native_quote_parent_independently_live_verified":False,
            "current_product_price_verified":False,
            "salesforce_save_allowed":False,
        })
    candidates.sort(key=lambda x:(x["quote_status"] or "",x["opportunity_id"],x["quote_id"]))
    status=Counter(x["quote_status"] for x in candidates)
    result={
        "source_quotation_count":audited["full_quotation_count"],
        "source_single_product_count":len(one),
        "structurally_one_to_one_candidates":len(candidates),
        "status_counts":dict(sorted(status.items())),
        "with_independently_verified_contact_oppo":sum(x["known_contact_opportunity_live_evidence"] for x in candidates),
        "native_quote_parent_verified_for_candidates":0,
        "auto_save_approved":0,
        "salesforce_writes":0,
    }
    return {"summary":result,"candidates":candidates}


def main():
    full=json.loads((ROOT/FULL).read_text(encoding="utf-8-sig"))
    one=json.loads((ROOT/ONE).read_text(encoding="utf-8-sig"))
    opps=json.loads((ROOT/OPPS).read_text(encoding="utf-8-sig"))
    evidence=json.loads((ROOT/EVIDENCE).read_text(encoding="utf-8-sig"))
    # Alias parser's full native-ID, five-flag, email and account validation;
    # unapproved rows cannot count as independently verified.
    valid=verified_private_aliases(evidence)
    approved_contacts={r["contact_id"] for r in valid["records"]}
    checked=[r for r in evidence if isinstance(r,dict) and r.get("contact_id") in approved_contacts]
    report=one_to_one_candidates(full,one,opps,checked)
    (ROOT/OUTPUT).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("OPPO_QUOTE_ONE_TO_ONE_SHORTLIST",json.dumps(report["summary"],sort_keys=True))


if __name__=="__main__":
    main()
