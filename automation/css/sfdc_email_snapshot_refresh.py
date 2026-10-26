#!/usr/bin/env python3
"""Refresh SFDC mail review snapshot from QQ while preserving all decisions.

Only the read-only Unanswered Emails A:U projection is replaced.
Email Review Decisions is append-only by UID; existing decisions are never overwritten.
"""
import os, json, base64, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
def value(row,i):
    return str(row[i]).strip() if len(row)>i and row[i] is not None else ""
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("Google credential is missing")
    try:key=json.loads(raw)
    except ValueError:key=json.loads(base64.b64decode(raw))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        key,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
    def read(book,tab,area):
        return api.get(spreadsheetId=book,range="'"+tab+"'!"+area,
                       valueRenderOption="FORMATTED_VALUE").execute().get("values",[])
    triage=read(QQ,"BI Unanswered Triage","A1:U1200")
    ledger=read(SFDC,"Email Review Decisions","A1:J1300")
    if not triage or value(triage[0],8)!="Thread UID":
        raise RuntimeError("Unexpected QQ triage columns; no writes performed")
    if not ledger or value(ledger[0],4)!="Mail UID (Key)":
        raise RuntimeError("Unexpected SFDC decision columns; no writes performed")
    items=[r for r in triage[1:] if value(r,8)]
    if len(items)>999:raise RuntimeError("SFDC snapshot limit exceeded; refusing truncation")
    existing={value(r,4) for r in ledger[1:] if value(r,4)}
    new=[]
    for r in items:
        uid=value(r,8)
        if uid in existing:continue
        existing.add(uid)
        new.append(["NONE",value(r,2),value(r,4),value(r,0),uid,value(r,16),
                    "","NOT_SUBMITTED","",value(r,3)])
    if len(ledger)-1+len(new)>1299:
        raise RuntimeError("SFDC decision ledger capacity exceeded")
    dry=os.getenv("DRY_RUN","true").lower()!="false"
    print(json.dumps({"dry_run":dry,"qq_triage":len(items),"new_decisions":len(new)},
                     ensure_ascii=False))
    if dry:return
    # A:U is an imported projection. V is a live formula and is never modified.
    api.clear(spreadsheetId=SFDC,range="'Unanswered Emails'!A2:U1000",body={}).execute()
    if items:
        api.update(spreadsheetId=SFDC,range="'Unanswered Emails'!A2",
                   valueInputOption="RAW",body={"values":[(r+[""]*21)[:21] for r in items]}).execute()
    if new:
        start=len(ledger)+1
        api.update(spreadsheetId=SFDC,range="'Email Review Decisions'!A"+str(start),
                   valueInputOption="RAW",body={"values":new}).execute()
    print("SFDC_MAIL_SNAPSHOT_REFRESH=PASS")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr)
        sys.exit(1)
