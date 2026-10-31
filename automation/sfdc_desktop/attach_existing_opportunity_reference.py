#!/usr/bin/env python3
"""Attach a read-only Salesforce existing Opportunity snapshot to a reviewed draft.

Never overwrites reviewed_draft.json. Never promotes historical values into
new Opportunity input fields. A user must verify source record identity first.
"""
import argparse
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--draft",required=True)
    p.add_argument("--snapshot",required=True)
    p.add_argument("--output",default="")
    args=p.parse_args()
    draft=json.loads(Path(args.draft).read_text(encoding="utf-8-sig"))
    snapshot=json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
    if snapshot.get("saved_or_modified") is not False or snapshot.get("source")!="Salesforce visible UI":
        p.error("Snapshot is not a verified read-only Salesforce UI capture")
    if draft.get("save_allowed") is not False:
        p.error("Draft must explicitly prohibit Salesforce Save")
    fields={}
    for frame in snapshot.get("frames",[]):
        for item in frame.get("fields",[]):
            label=str(item.get("label","")).strip()
            value=str(item.get("value","")).strip()
            if label and value:
                fields.setdefault(label,[]).append(value)
    fields={label:sorted(set(values)) for label,values in fields.items()}
    preferred=("Opportunity Name","Account Name","Main Contact","Amount",
               "Opportunity Currency","Close Date","Service Line","Stage",
               "Forecast Category","Progress Description","Status")
    catalog_id=str(draft.get("source_opportunity_id") or "").strip()
    live_id=str(snapshot.get("record_id_from_url") or "").strip()
    if live_id and catalog_id and live_id==catalog_id:
        identity="VERIFIED_ID_MATCH"
    elif live_id and catalog_id and len(live_id)>=15 and len(catalog_id)>=15 and live_id[:15]==catalog_id[:15]:
        identity="VERIFIED_ID_MATCH_15_PREFIX"
    elif live_id and catalog_id:
        identity="ID_MISMATCH"
    else:
        identity="NOT_VERIFIED"
    result={
        "version":"sfdc-opportunity-reference-v1",
        "source_opportunity_id_from_catalog":draft.get("source_opportunity_id"),
        "source_opportunity_name_from_catalog":draft.get("Existing Opportunity Name (reference only)"),
        "source_page_title":snapshot.get("title"),
        "identity_match":identity,
        "source_opportunity_id_from_salesforce_url":live_id or None,
        "note":"Only Lightning Opportunity route ID can verify identity; mismatch blocks historical reuse.",
        "fields_from_live_ui":fields,
        "missing_preferred_fields":[x for x in preferred if x not in fields],
        "conflicting_field_values":{k:v for k,v in fields.items() if len(v)>1},
        "new_opportunity_input":{k:draft.get(k,"") for k in preferred if k!="Opportunity Currency"},
        "save_allowed":False,
        "salesforce_save_performed":False
    }
    target=Path(args.output) if args.output else Path(args.draft).with_name("existing_opportunity_reference.json")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("LIVE UI FIELDS:",len(fields))
    print("MISSING PREFERRED:",", ".join(result["missing_preferred_fields"]) or "none")
    print("SOURCE IDENTITY:",identity,"(historical values are reference-only)")
    print("REPORT:",target)
    print("READ ONLY. New Opportunity draft left unchanged.")
if __name__=="__main__":
    main()
