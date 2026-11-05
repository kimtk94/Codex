#!/usr/bin/env python3
"""Conservative service-label coverage of *all* 1:1 Quote learning candidates.

Only exact service tokens in historical Opportunity names can create a
NAME_HINT_ONLY label; single historical Product record does NOT by itself
prove single service. Unknown/ambiguous/multi-service names remain manual.
Never prints customer text, IDs, emails, names, amounts or sales prices.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path.home()/".sfdc_desktop"
SHORTLIST="one_to_one_oppo_quote_learning_shortlist_PRIVATE.json"
MANIFEST="oppo_quote_single_product_learning_manifest_PRIVATE.json"
OUT="one_to_one_service_pattern_counts_PRIVATE.json"

TOKENS={
 "PMP":re.compile(r"(?<![A-Za-z0-9])PMP(?![A-Za-z0-9])",re.I),
 "mRNA":re.compile(r"(?<![A-Za-z0-9])mRNA(?![A-Za-z0-9])",re.I),
 "WGS":re.compile(r"(?<![A-Za-z0-9])WGS(?![A-Za-z0-9])",re.I),
 "WES":re.compile(r"(?<![A-Za-z0-9])WES(?![A-Za-z0-9])",re.I),
 "DIA":re.compile(r"(?<![A-Za-z0-9])(?:Deep|Rapid)?\s*DIA(?![A-Za-z0-9])",re.I),
 "16S":re.compile(r"(?<![A-Za-z0-9])16S(?![A-Za-z0-9])",re.I),
 "scRNA":re.compile(r"(?<![A-Za-z0-9])(?:10x|scRNA|single.cell)(?![A-Za-z0-9])",re.I),
 "Olink":re.compile(r"(?<![A-Za-z0-9])Olink(?![A-Za-z0-9])",re.I),
 "Visium":re.compile(r"(?<![A-Za-z0-9])Visium(?![A-Za-z0-9])",re.I)
}


def classify_name(name):
    if not isinstance(name,str) or not name.strip():
        return "HOLD_UNCLASSIFIED_NAME"
    hits=[service for service,rx in TOKENS.items() if rx.search(name)]
    if len(hits)==1:
        return "NAME_HINT_ONLY_"+hits[0]
    if not hits:
        return "HOLD_UNCLASSIFIED_NAME"
    return "HOLD_MULTIPLE_SERVICE_HINTS"


def classify_shortlist(shortlist,manifest):
    if not isinstance(shortlist,dict) or not isinstance(manifest,list):
        raise ValueError("INVALID_PRIVATE_SOURCE")
    candidates=shortlist.get("candidates")
    expected=shortlist.get("summary",{}).get("structurally_one_to_one_candidates")
    if not isinstance(candidates,list) or len(candidates)!=expected:
        raise ValueError("INCONSISTENT_ONE_TO_ONE_COHORT")
    by_id={}
    for r in manifest:
        if not isinstance(r,dict) or not isinstance(r.get("quote_id"),str):
            raise ValueError("INVALID_MANIFEST_ENTRY")
        if r["quote_id"] in by_id:
            raise ValueError("DUPLICATE_QUOTE_ID")
        by_id[r["quote_id"]]=r
    stats=Counter()
    for row in candidates:
        if not isinstance(row,dict):
            raise ValueError("INVALID_CANDIDATE")
        q=by_id.get(row.get("quote_id"))
        if (q is None or q.get("oppo_id")!=row.get("opportunity_id") or
                row.get("single_product_snapshot") is not True or
                row.get("snapshot_opportunity_and_contact_labels_match") is not True or
                row.get("quote_name_unique_in_full_inventory") is not True or
                row.get("salesforce_save_allowed") is not False):
            raise ValueError("UNVERIFIED_STRUCTURAL_CANDIDATE")
        stats[classify_name(q.get("oppo_name"))]+=1
    return {
        "total_structural_candidates":len(candidates),
        "service_label_counts":dict(sorted(stats.items())),
        "current_product_catalog_verified":False,
        "single_service_confirmed_from_name":False,
        "prices_verified":False,
        "salesforce_save_allowed":False,
        "salesforce_writes":0,
    }


def main():
    shortlist=json.loads((ROOT/SHORTLIST).read_text(encoding="utf-8-sig"))
    manifest=json.loads((ROOT/MANIFEST).read_text(encoding="utf-8-sig"))
    report=classify_shortlist(shortlist,manifest)
    (ROOT/OUT).write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
    print("ONE_TO_ONE_SERVICE_HINTS",json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
