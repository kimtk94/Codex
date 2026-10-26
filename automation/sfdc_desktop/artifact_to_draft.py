#!/usr/bin/env python3
"""Validate a GitHub Actions Opportunity search artifact and make a reviewed draft.
No Salesforce API, browser access, or Save operation.
"""
import argparse
import json
from pathlib import Path

def prepare(report, index=0):
    if report.get("salesforce_save_performed") is not False:
        raise ValueError("Untrusted artifact: save safety marker missing")
    matches=report.get("matches")
    if not isinstance(matches,list) or not matches:
        raise ValueError("No matching Opportunities")
    if not 0 <= index < len(matches):
        raise ValueError("Candidate index out of range")
    selected=matches[index]
    required=("opportunity_id","account","contact")
    if not all(str(selected.get(k,"")).strip() for k in required):
        raise ValueError("Selected Opportunity missing identity fields")
    from catalog_reuse import make_draft
    draft=make_draft(selected)
    draft["lookup_verified"]=False
    draft["save_allowed"]=False
    draft["selection_index"]=index
    return draft

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--matches",required=True)
    p.add_argument("--index",type=int,default=0)
    p.add_argument("--output",default="")
    args=p.parse_args()
    result=json.loads(Path(args.matches).read_text(encoding="utf-8-sig"))
    draft=prepare(result,args.index)
    target=Path(args.output) if args.output else Path(args.matches).with_name("reviewed_draft.json")
    target.write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Draft prepared for review:",target)
    print("Salesforce write: DISABLED. Verify Account/Contact in Lightning UI before any write.")
if __name__=="__main__":
    main()
