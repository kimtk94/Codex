#!/usr/bin/env python3
"""Read-only recovery gate for missed 09/12/17 KST SFDC mail subscriptions."""
import datetime as dt
import json, os, sys, urllib.parse
from report_fallback_gate import BOOK, KST, REQUIRED, SOURCE_HEADER, parse_kst_stamp

SLOTS=((9,0),(12,0),(17,0))
def latest_due(now, grace_minutes=40):
    if now.tzinfo is None:raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
    now=now.astimezone(KST)
    return next((slot for h,m in reversed(SLOTS)
        if now >= (slot:=dt.datetime.combine(now.date(),dt.time(h,m),tzinfo=KST))+dt.timedelta(minutes=grace_minutes)),None)

def inspect(rows,now,min_retry_minutes=95):
    due=latest_due(now)
    if due is None:return False,"BEFORE_FIRST_REPORT_DUE","NONE"
    if not rows or rows[0][:len(SOURCE_HEADER)]!=SOURCE_HEADER:
        raise ValueError("SFDC_INGEST_AUDIT_SCHEMA_CHANGED")
    by={}
    for r in rows[1:]:
        if not r or r[0] not in REQUIRED:continue
        if r[0] in by:raise ValueError("DUPLICATE_SFDC_AUDIT_ENTITY")
        if len(r)<10 or r[8] not in ("STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT"):
            raise ValueError("UNVERIFIED_SFDC_AUDIT_ENTITY")
        if len(r[7])!=64 or any(c not in "0123456789abcdef" for c in r[7]):
            raise ValueError("REPORT_HASH_MISSING_OR_INVALID")
        if not r[3].isdigit() or not r[4].isdigit() or r[6]!="0" or min(int(r[3]),int(r[4]))<1:
            raise ValueError("REPORT_ROW_COUNTS_INVALID")
        by[r[0]]=r
    if set(by)!=set(REQUIRED):raise ValueError("SFDC_AUDIT_ENTITY_MISSING")
    current=now.astimezone(KST)
    checked=[parse_kst_stamp(by[name][2]) for name in REQUIRED]
    received=[parse_kst_stamp(by[name][1]) for name in REQUIRED]
    if any(stamp>current+dt.timedelta(minutes=10) for stamp in checked+received):
        raise ValueError("SFDC_AUDIT_TIMESTAMP_IN_FUTURE")
    stamp=due.strftime("%Y-%m-%d %H:%M KST")
    if all(t>=due for t in received):
        return False,"ALL_REPORTS_RECEIVED_FOR_SLOT",stamp
    if (current-max(checked)).total_seconds()/60<min_retry_minutes:
        return False,"NO_NEW_REPORT_RETRY_THROTTLED",stamp
    return True,"MISSING_REPORT_FOR_SLOT_RETRY_INGEST",stamp

def main():
    secret=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not secret:raise RuntimeError("READ_ONLY_SHEET_CREDENTIAL_MISSING")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    c=service_account.Credentials.from_service_account_info(json.loads(secret),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+urllib.parse.quote("'SFDC Email Ingest Audit'!A1:J10",safe="")
    response=AuthorizedSession(c).get(url,timeout=40)
    response.raise_for_status()
    refresh,reason,slot=inspect(response.json().get("values",[]),dt.datetime.now(KST))
    file=os.environ.get("GITHUB_OUTPUT")
    if not file:raise RuntimeError("GITHUB_OUTPUT_NOT_SET")
    with open(file,"a",encoding="utf-8") as f:
        f.write("refresh="+str(refresh).lower()+"\nreason="+reason+"\n")
    print("SFDC_REPORT_SLOT_RECOVERY="+reason+" expected="+slot)
    print("STAGING_ONLY;NO_CUSTOMER_SEND;NO_SFDC_SAVE")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("SFDC_REPORT_RECOVERY_GATE_ERROR="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
