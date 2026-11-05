#!/usr/bin/env python3
"""Read-only aggregate reconciliation of the complete local SFDC inventories.

Inputs are private authenticated workstation snapshots. The 862-Quote index
is a complete snapshot listing, NOT proof that 862 detail records have been
re-read live in this run. Counts never auto-authorize Save, prices or links.
Do not send raw customer data, emails, names or IDs to GitHub.
"""
import json
import re
from collections import Counter,defaultdict
from pathlib import Path

from contact_oppo_selection import excluded_account
from oppo_quote_case_learning import classify_case

ROOT=Path.home()/".sfdc_desktop"
FULL="all_quotation_inventory_20261103_PRIVATE.json"
ONE="oppo_quote_single_product_learning_manifest_PRIVATE.json"
OPPS="oppo_linked_contact_candidate_manifest_PRIVATE.json"
OUTPUT="full_oppo_quote_snapshot_reconciliation_PRIVATE.json"
NATIVE_QUOTE=re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
NATIVE_OPP=re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")


def summary(full,one,opps):
    if not isinstance(full,dict) or not isinstance(one,list) or not isinstance(opps,list):
        raise ValueError("INVALID_SNAPSHOT_TYPES")
    if full.get("fully_enumerated") is not True or full.get("limit_reached") is not False:
        raise ValueError("UNTRUSTED_INCOMPLETE_QUOTE_SNAPSHOT")
    entries=full.get("rows")
    if not isinstance(entries,list):
        raise ValueError("INVALID_FULL_QUOTE_ROWS")
    all_ids=[r.get("id") for r in entries if isinstance(r,dict)]
    if len(all_ids)!=len(entries) or len(set(all_ids))!=len(all_ids) or not all(
        isinstance(x,str) and NATIVE_QUOTE.fullmatch(x) for x in all_ids
    ):
        raise ValueError("DUPLICATE_OR_INVALID_COMPLETE_QUOTE_ID")
    all_set=set(all_ids)
    one_ids=[]
    for r in one:
        if not isinstance(r,dict):
            raise ValueError("INVALID_LEARNED_QUOTE_RECORD")
        native=r.get("quote_id")
        if not isinstance(native,str) or not NATIVE_QUOTE.fullmatch(native):
            raise ValueError("INVALID_SINGLE_PRODUCT_QUOTE_ID")
        one_ids.append(native)
    if len(set(one_ids))!=len(one_ids) or not set(one_ids).issubset(all_set):
        raise ValueError("LEARNED_QUOTES_MUST_BE_UNIQUE_SUBSET_OF_FULL")
    opp_index={}
    for r in opps:
        if not isinstance(r,dict):
            raise ValueError("INVALID_OPPORTUNITY_ROW")
        ident=r.get("opportunity_id")
        if not isinstance(ident,str) or not NATIVE_OPP.fullmatch(ident) or ident in opp_index:
            raise ValueError("DUPLICATE_OR_INVALID_OPPORTUNITY_ID")
        opp_index[ident]=r
    statuses=Counter()
    relation=Counter()
    name_check=Counter()
    unit=Counter()
    by_opp=Counter()
    for r in one:
        statuses[str(r.get("quote_status") or "UNKNOWN")]+=1
        opp_id=r.get("oppo_id")
        if not isinstance(opp_id,str) or not NATIVE_OPP.fullmatch(opp_id):
            relation["invalid_parent_ref"]+=1
            continue
        by_opp[opp_id]+=1
        opp=opp_index.get(opp_id)
        if not opp:
            relation["parent_not_in_in_scope_opportunity_snapshot"]+=1
        elif excluded_account(opp.get("institution_hint")):
            relation["explicit_excluded_institution"]+=1
        else:
            relation["parent_id_in_in_scope_opportunity_snapshot"]+=1
            if (r.get("oppo_name") or "").strip()==(opp.get("opportunity_name") or "").strip():
                name_check["oppo_name_exact_snapshot_match"]+=1
            else:
                name_check["oppo_name_snapshot_mismatch_or_missing"]+=1
            if (r.get("contact_display") or "").strip()==(opp.get("contact_display") or "").strip():
                name_check["contact_label_exact_snapshot_match"]+=1
            else:
                name_check["contact_label_mismatch_or_missing"]+=1
        q=str(r.get("quote_name") or "")
        oppname=str(r.get("oppo_name") or "")
        if q and oppname and (q==oppname or q.startswith(oppname+"-")):
            name_check["quote_name_starts_with_oppo_name"]+=1
        else:
            name_check["quote_name_does_not_start_with_oppo_name"]+=1
        classification=classify_case(oppname)
        unit[classification["status"]]+=1
        if classification["modes"]==["PE250"]:
            unit["explicit_pe250"]+=1
            unit["explicit_pe250_"+classification["status"]]+=1
    repeated=sum(n for n in by_opp.values() if n>1)
    # The fixed 16-column Quotation list layout is cross-checked against
    # every known single-Product row before using it for the other 450.
    row_by_id={r["id"]:r["cells"] for r in entries}
    if any(not isinstance(cells,list) or len(cells)!=16 for cells in row_by_id.values()):
        raise ValueError("QUOTE_LIST_COLUMN_LAYOUT_CHANGED")
    for r in one:
        cells=row_by_id[r["quote_id"]]
        if (r.get("quote_name")!=cells[2] or
            r.get("oppo_name")!=cells[4] or
            r.get("quote_status")!=cells[5]):
            raise ValueError("QUOTE_LIST_COLUMNS_NOT_VERIFIED")
    names=Counter(r.get("opportunity_name") for r in opp_index.values()
                  if isinstance(r.get("opportunity_name"),str) and r["opportunity_name"])
    other_rows=[row_by_id[qid] for qid in all_set-set(one_ids)]
    other_status=Counter(str(c[5] or "UNKNOWN") for c in other_rows)
    other_name_matches=Counter()
    for cells in other_rows:
        n=names.get(cells[4],0)
        if n==0:
            other_name_matches["none"]+=1
        elif n==1:
            other_name_matches["unique_name_only_not_native_id"]+=1
        else:
            other_name_matches["multiple_in_scope_opportunity_names"]+=1
    return {
        "scope":"PRIVATE_PREVIOUSLY_ENUMERATED_SNAPSHOT_NOT_LIVE_FULL_RECORD_RECHECK",
        "full_quotation_snapshot_enumerated":True,
        "full_quotation_count":len(all_ids),
        "one_product_manifest_count":len(one_ids),
        "non_one_product_or_unclassified_quote_count":len(all_ids)-len(one_ids),
        "in_scope_opportunity_snapshot_count":len(opp_index),
        "other_quote_status_counts":dict(sorted(other_status.items())),
        "other_quote_opportunity_name_lookup":dict(sorted(other_name_matches.items())),
        "other_quote_native_parent_ids_verified":False,
        "quote_status_counts":dict(sorted(statuses.items())),
        "opportunity_relation_counts":dict(sorted(relation.items())),
        "name_comparison_counts":dict(sorted(name_check.items())),
        "case_unit_policy_counts":dict(sorted(unit.items())),
        "unique_opportunity_refs_in_single_product_quote_manifest":len(by_opp),
        "opportunity_refs_with_multiple_quotes":sum(1 for n in by_opp.values() if n>1),
        "quote_rows_on_multi_quote_opportunities":repeated,
        "native_parent_link_independently_verified_for_all":False,
        "current_product2_and_pricebook_verified_for_all":False,
        "quotes_approved_for_automatic_save":0,
        "salesforce_writes":0
    }


def main():
    full=json.loads((ROOT/FULL).read_text(encoding="utf-8-sig"))
    one=json.loads((ROOT/ONE).read_text(encoding="utf-8-sig"))
    opps=json.loads((ROOT/OPPS).read_text(encoding="utf-8-sig"))
    report=summary(full,one,opps)
    (ROOT/OUTPUT).write_text(json.dumps(report,sort_keys=True,indent=2),encoding="utf-8")
    print("ALL_SFDC_QUOTE_SNAPSHOT_AUDIT",json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
