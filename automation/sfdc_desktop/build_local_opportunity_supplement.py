#!/usr/bin/env python3
"""Build a local, read-only supplementary Opportunity record from a live SFDC snapshot.

Does not modify Google Sheets, historical Catalog, Salesforce, or any reviewed draft.
"""
import argparse
import json
import re
from pathlib import Path

FIELDS = ("Opportunity Name", "Account Name", "Main Contact", "Amount",
          "Opportunity Currency", "Close Date", "Service Line", "Stage",
          "Forecast Category", "Progress Description", "Status")

def build(snapshot):
    record_id=str(snapshot.get("record_id_from_url") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?",record_id):
        raise ValueError("Snapshot has no valid record ID")
    if snapshot.get("record_id_evidence")!="lightning_opportunity_route":
        raise ValueError("Opportunity ID must come from Lightning Opportunity route")
    if snapshot.get("source")!="Salesforce visible UI" or snapshot.get("saved_or_modified") is not False:
        raise ValueError("Snapshot must be read-only Salesforce UI data")
    items={}
    for frame in snapshot.get("frames",[]):
        for item in frame.get("fields",[]):
            label=str(item.get("label") or "").strip()
            value=str(item.get("value") or "").strip()
            if label in FIELDS and value:
                items.setdefault(label,set()).add(value)
    resolved={k:next(iter(values)) for k,values in items.items() if len(values)==1}
    conflicts={k:sorted(values) for k,values in items.items() if len(values)>1}
    return {
        "version":"sfdc-local-supplement-v1",
        "record_id":record_id,
        "catalog_membership":"NOT_FOUND_IN_CATALOG_AT_LOOKUP",
        "source":"Salesforce visible UI",
        "identity_evidence":"lightning_opportunity_route",
        "fields":resolved,
        "conflicting_fields":conflicts,
        "missing_fields":[k for k in FIELDS if k not in resolved],
        "verification":"UI_CAPTURE_NOT_CATALOG_RECONCILED",
        "save_allowed":False,
        "sfdc_write_performed":False,
        "google_sheet_write_performed":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",required=True)
    p.add_argument("--matches",required=True,help="Exact-ID Catalog lookup result (NOT_FOUND required)")
    p.add_argument("--output",default="")
    a=p.parse_args()
    snapshot=json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
    lookup=json.loads(Path(a.matches).read_text(encoding="utf-8-sig"))
    if lookup.get("lookup_status")!="NOT_FOUND" or lookup.get("matches")!=[]:
        p.error("Expected explicit NOT_FOUND Catalog lookup artifact with no matches")
    entry=build(snapshot)
    output=Path(a.output) if a.output else Path(a.snapshot).with_name("sfdc_local_supplement.json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SOURCE ID:",entry["record_id"])
    print("LIVE FIELDS:",len(entry["fields"]))
    print("MISSING FIELDS:",", ".join(entry["missing_fields"]) or "none")
    print("REPORT:",output)
    print("Local reference only. Catalog and Salesforce unchanged.")

if __name__=="__main__":
    main()
