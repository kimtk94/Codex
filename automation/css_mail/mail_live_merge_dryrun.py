#!/usr/bin/env python3
"""Run production canonical mail overlap plan. Strictly read-only."""
import json,os,sys
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from mail_migration_inventory import fetch,BOOK
from mail_canonical_merge_plan import plan

def main():
    cred=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s=AuthorizedSession(cred)
    old=fetch(s,"All Emails","A1:N50000")
    staging=fetch(s,"CSS Git Ingest","A1:R50000")
    result=plan(old,staging)
    print("CSS_MAIL_LIVE_MERGE_PLAN "+json.dumps(result,sort_keys=True))
    if result["cutover_allowed"] or result["automatic_deletion_allowed"]:
        raise RuntimeError("UNSAFE_CUTOVER_FLAG")
    return 0
if __name__=="__main__":
    try:sys.exit(main())
    except Exception as e:
        print("CSS_MAIL_LIVE_MERGE_ERROR "+type(e).__name__+":"+str(e)[:160],file=sys.stderr)
        sys.exit(1)
