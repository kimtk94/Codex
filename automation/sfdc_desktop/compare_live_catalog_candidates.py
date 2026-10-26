#!/usr/bin/env python3
"""Read-only comparison of a live Salesforce Opportunity snapshot with Catalog matches."""
import argparse
import json
import re
from pathlib import Path

def norm(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip().casefold()

def num(value):
    x=re.sub(r"[^0-9.\\-]", "", str(value or ""))
    try:return float(x)
    except ValueError:return None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--matches",required=True)
    p.add_argument("--snapshot",required=True)
    p.add_argument("--output",default="")
    a=p.parse_args()
    report=json.loads(Path(a.matches).read_text(encoding="utf-8-sig"))
    snap=json.loads(Path(a.snapshot).read_text(encoding="utf-8-sig"))
    if snap.get("source")!="Salesforce visible UI" or snap.get("saved_or_modified") is not False:
        p.error("Invalid read-only Salesforce snapshot")
    fields={}
    for frame in snap.get("frames",[]):
        for field in frame.get("fields",[]):
            k=str(field.get("label","")).strip()
            v=str(field.get("value","")).strip()
            if k and v:fields.setdefault(k,set()).add(v)
    web={k:next(iter(v)) for k,v in fields.items() if len(v)==1}
    comparisons=[]
    for m in report.get("matches",[]):
        checks={}
        for label,key in (("Opportunity Name","opportunity_name"),
                          ("Account Name","account"),("Main Contact","contact"),
                          ("Amount","historical_amount"),
                          ("Close Date","historical_close_date")):
            actual=web.get(label)
            expected=m.get(key)
            if not actual or not expected:checks[label]="UNAVAILABLE"
            elif label=="Amount":
                av,bv=num(actual),num(expected)
                checks[label]="MATCH" if av is not None and av==bv else "MISMATCH"
            elif label=="Close Date":
                # Date display formats vary; do not assert mismatch without normalization.
                checks[label]="TEXT_MATCH" if norm(actual)==norm(expected) else "NEEDS_DATE_NORMALIZATION"
            else:
                checks[label]="MATCH" if norm(actual)==norm(expected) else "MISMATCH"
        comparisons.append({"catalog_business_id":m.get("opportunity_id"),
                            "catalog_stage":m.get("historical_stage"),
                            "catalog_created_date":m.get("historical_created_date"),
                            "checks":checks})
    result={"version":"live-catalog-evidence-v1",
            "web_record_id":snap.get("record_id_from_url"),
            "matches":comparisons,
            "record_id_mapping":"NOT_VERIFIED",
            "save_allowed":False}
    target=Path(a.output) if a.output else Path(a.matches).with_name("live_catalog_comparison.json")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("WEB RECORD ID:",result["web_record_id"])
    for row in comparisons:
        print("CATALOG:",row["catalog_business_id"],"STAGE:",row["catalog_stage"],"CHECKS:",json.dumps(row["checks"],ensure_ascii=False))
    print("REPORT:",target)
    print("READ ONLY; record ID mapping remains unverified.")
if __name__=="__main__":main()
