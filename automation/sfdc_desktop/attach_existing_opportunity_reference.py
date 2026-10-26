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
    result={
        "version":"sfdc-opportunity-reference-v1",
        "source_opportunity_id_from_catalog":draft.get("source_opportunity_id"),
        "source_opportunity_name_from_catalog":draft.get("Existing Opportunity Name (reference only)"),
        "source_page_title":snapshot.get("title"),
        "identity_match":"NOT_VERIFIED",
        "note":"A Salesforce page title or matching name does NOT prove record ID. Confirm the source record manually.",
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
    print("SOURCE IDENTITY: NOT_VERIFIED (do not auto-copy historical values)")
    print("REPORT:",target)
    print("READ ONLY. New Opportunity draft left unchanged.")
if __name__=="__main__":
    main()
