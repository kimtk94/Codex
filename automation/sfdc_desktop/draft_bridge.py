#!/usr/bin/env python3
"""Read-only Catalog to Salesforce draft bridge. Never invokes Salesforce or saves."""
import argparse
import json
import sys
from pathlib import Path
from catalog_reuse import load_sheet, load_csv, search, dedupe, make_draft

def main():
    parser=argparse.ArgumentParser(description="Prepare reviewed SFDC draft from live Sheet, no Salesforce writes")
    parser.add_argument("--csv",default="",help="Use a local artifact CSV instead of Google credentials")
    parser.add_argument("--account",default="")
    parser.add_argument("--contact",default="")
    parser.add_argument("--service",default="")
    parser.add_argument("--output",default="")
    args=parser.parse_args()
    if not any((args.account.strip(),args.contact.strip(),args.service.strip())):
        parser.error("Provide account, contact, or service")
    rows=load_csv(args.csv) if args.csv else load_sheet()
    matches=search(rows,args.account,args.contact,args.service,top=10)
    report={"status":"REVIEW_REQUIRED" if matches else "NO_MATCH","total_unique_opportunities":len(dedupe(rows)),
        "matches":matches,
        "draft":make_draft(matches[0]) if matches else None,
        "lookup_verified":False,"save_allowed":False}
    if args.output:
        target=Path(args.output)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Draft created locally for human review:",target)
    else:
        # Never dump customer identities to an unexpected CI log.
        print(json.dumps({"status":report["status"],"match_count":len(matches),"save_allowed":False}))
if __name__=="__main__":
    main()
