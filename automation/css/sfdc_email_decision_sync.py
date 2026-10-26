#!/usr/bin/env python3
"""Apply explicit SFDC email decisions to the existing QQ mail review ledger.

Default is dry-run. The existing bi_mail_review_sync.py then applies the
ledger decisions to mail/sender exclusions. Decisions remain keyed by UID.
"""
import os
import json
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
ACTIONS={"EXCLUDE_MAIL","EXCLUDE_SENDER","RESTORE_MAIL","RESTORE_SENDER"}
def cell(row, i):
    return str(row[i]).strip() if i<len(row) and row[i] is not None else ""
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GCP_SA_KEY") or os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not raw:raise RuntimeError("Missing Google service account credentials")
    try:credentials=json.loads(raw)
    except ValueError:
        import base64
        credentials=json.loads(base64.b64decode(raw))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        credentials,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
    def read(book, tab):
        return api.get(spreadsheetId=book,range="'"+tab+"'!A2:J1300").execute().get("values",[])
    src=read(SFDC,"Email Review Decisions")
    dst=read(QQ,"BI Mail Review & Exclusions")
    by_uid={cell(r,4):(i,r) for i,r in enumerate(dst,start=2) if cell(r,4)}
    updates=[];new=[];pending=[];conflicts=[]
    for i,row in enumerate(src,start=2):
        uid=cell(row,4);action=cell(row,0).upper()
        if not uid or action not in ACTIONS:continue
        existing=by_uid.get(uid)
        if existing:
            j,qq=existing
            previous=cell(qq,0).upper();status=cell(qq,7)
            if previous==action:continue
            if previous not in ("","NONE") and not status.startswith("SYNCED:"):
                conflicts.append(uid);continue
            updates.extend([
                {"range":"'BI Mail Review & Exclusions'!A"+str(j),"values":[[action]]},
                {"range":"'BI Mail Review & Exclusions'!H"+str(j),"values":[["NOT_SUBMITTED"]]}])
        else:
            new.append([action,cell(row,1),cell(row,2),cell(row,3),
                        uid,cell(row,5),cell(row,6),"NOT_SUBMITTED",
                        cell(row,8),cell(row,9)])
        pending.append(uid)
    summary={"dry_run":os.getenv("DRY_RUN","true").lower()!="false",
             "updates":len(updates)//2,"new":len(new),
             "conflicts":conflicts,"pending_uids":len(pending)}
    print(json.dumps(summary,ensure_ascii=False))
    if conflicts:raise RuntimeError("Conflicting unsynced reviewer actions: "+",".join(conflicts))
    if summary["dry_run"]:return
    if updates:api.batchUpdate(spreadsheetId=QQ,body={"valueInputOption":"RAW","data":updates}).execute()
    if new:api.append(spreadsheetId=QQ,range="'BI Mail Review & Exclusions'!A1",
        valueInputOption="RAW",insertDataOption="INSERT_ROWS",
        body={"values":new}).execute()
    print("SFDC_DECISIONS_QUEUED_TO_QQ",len(pending))
if __name__=="__main__":
    try:main()
    except Exception as error:
        print(type(error).__name__+": "+str(error),file=sys.stderr)
        sys.exit(1)
