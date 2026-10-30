#!/usr/bin/env python3
"""Fail-closed read-only freshness gate for extra weekday SFDC report recovery.
Only the 13:27 KST backup uses this script. Never reads customer-level rows,
sends email, writes CRM, or modifies Sheets.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo

KST=ZoneInfo("Asia/Seoul")
BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
REQUIRED=("Leads","Opportunities","Quotation")
SOURCE_HEADER=["Entity","Source Received KST","Ingest Checked KST","Rows","Unique IDs",
               "Duplicate IDs","Missing IDs","Content SHA256","State","Source Kind"]

def parse_kst_stamp(value):
    if not isinstance(value,str) or not value.endswith(" KST"):
        raise ValueError("INVALID_AUDIT_TIMESTAMP")
    try:
        stamp=dt.datetime.strptime(value[:-4],"%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("INVALID_AUDIT_TIMESTAMP") from exc
    return stamp.replace(tzinfo=KST)

def needs_backup(rows,now,max_age_min=90):
    if now.tzinfo is None: raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")
    if not rows or rows[0][:10]!=SOURCE_HEADER:
        raise ValueError("SFDC_INGEST_AUDIT_SCHEMA_CHANGED")
    by_entity={}
    for row in rows[1:]:
        if not row or row[0] not in REQUIRED:
            continue
        if row[0] in by_entity:
            raise ValueError("DUPLICATE_SFDC_AUDIT_ENTITY")
        if len(row)<10:
            raise ValueError("INCOMPLETE_SFDC_AUDIT_RECORD")
        by_entity[row[0]]=row
    missing=[label for label in REQUIRED if label not in by_entity]
    if missing: raise ValueError("SFDC_AUDIT_ENTITY_MISSING")
    ages=[]
    for entity in REQUIRED:
        row=by_entity[entity]
        stamp=parse_kst_stamp(row[2])
        age=(now.astimezone(KST)-stamp).total_seconds()/60
        if age< -10:raise ValueError("SFDC_AUDIT_TIMESTAMP_IN_FUTURE")
        ages.append(age)
        if row[8]!="STAGED_NOT_PROMOTED":
            # Do not infer healthy data from a successful GitHub workflow.
            return True
    return any(age>max_age_min for age in ages)

def main():
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("READ_ONLY_SHEET_CREDENTIAL_MISSING")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credentials=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    client=AuthorizedSession(credentials)
    cell=urllib.parse.quote("'SFDC Email Ingest Audit'!A1:J10",safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+cell
    response=client.get(url,timeout=40)
    response.raise_for_status()
    rows=response.json().get("values",[])
    decision=needs_backup(rows,dt.datetime.now(KST))
    result="true" if decision else "false"
    output=os.getenv("GITHUB_OUTPUT")
    if not output:raise RuntimeError("GITHUB_OUTPUT_NOT_SET")
    with open(output,"a",encoding="utf-8") as f:
        f.write("refresh="+result+"\n")
    print("SFDC_BACKUP_GATE="+("NEEDS_REFRESH" if decision else "ALREADY_FRESH"))
    print("SFDC_BACKUP_BOUNDARY=SOURCE_AUDIT_ONLY; NO_REPORT_CONTENT_READ; NO_CRM_SAVES")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("SFDC_BACKUP_GATE_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
