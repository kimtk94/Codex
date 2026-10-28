#!/usr/bin/env python3
"""Read-only mail migration inventory. No raw messages are modified."""
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
def fetch(session,tab,area):
    address=urllib.parse.quote("'"+tab+"'!"+area,safe="")
    r=session.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+address,timeout=90)
    r.raise_for_status()
    return r.json().get("values",[])
def value(row,i):
    return str(row[i]).strip() if len(row)>i and row[i] is not None else ""
def run():
    creds=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    old=fetch(session,"All Emails","A1:N50000")
    new=fetch(session,"CSS Git Ingest","A1:R50000")
    if not old or old[0][:3]!=["uid","message_id","received_at"]:raise RuntimeError("LEGACY_SCHEMA_CHANGED")
    if not new or new[0][:5]!=["ingest_key","message_id","imap_uid","folder","uidvalidity"]:raise RuntimeError("STAGING_SCHEMA_CHANGED")
    legacy=[r for r in old[1:] if value(r,0)]
    staging=[r for r in new[1:] if value(r,0)]
    old_ids={value(r,1).strip().lower() for r in legacy if value(r,1)}
    new_ids={value(r,1).strip().lower() for r in staging if value(r,1)}
    old_attachments=sum(bool(value(r,9)) for r in legacy)
    old_invoice_attachments=sum(bool(re.search(r"TAX\\s*INVOICE",value(r,9),re.I)) for r in legacy)
    malformed=sum(not re.fullmatch(r"[^|]+\|[0-9]+\|[0-9]+",value(r,0)) for r in staging)
    keys=[value(r,0) for r in staging]
    report={
        "legacy_rows":len(legacy),"staging_rows":len(staging),
        "legacy_distinct_message_ids":len(old_ids),"staging_distinct_message_ids":len(new_ids),
        "shared_message_ids":len(old_ids & new_ids),"legacy_only_message_ids":len(old_ids-new_ids),
        "staging_only_message_ids":len(new_ids-old_ids),
        "legacy_rows_with_attachments":old_attachments,
        "legacy_rows_with_invoice_attachments":old_invoice_attachments,
        "staging_duplicate_ingest_keys":len(keys)-len(set(keys)),
        "staging_malformed_ingest_keys":malformed,
        "legacy_missing_uidvalidity":True,
        "legacy_attachment_migration_complete":False,
        "cutover_allowed":False
    }
    print("CSS_MAIL_MIGRATION_INVENTORY "+json.dumps(report,sort_keys=True))
    if malformed or report["staging_duplicate_ingest_keys"]:return 2
    return 0
if __name__=="__main__":
    try:sys.exit(run())
    except Exception as exc:
        print("CSS_MAIL_MIGRATION_ERROR "+type(exc).__name__+":"+str(exc)[:150],file=sys.stderr)
        sys.exit(1)
