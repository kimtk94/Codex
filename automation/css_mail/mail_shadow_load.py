#!/usr/bin/env python3
"""Append-only shadow migration. Original tabs, IMAP checkpoints and consumers untouched."""
import json,os,sys,urllib.parse
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from mail_canonical_merge_plan import get,legacy_key,staging_key,plan

BOOK=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
TAB="Canonical Mail Ledger"
COLS=["canonical_key","source_table","source_row","legacy_uid","imap_folder","imap_uid","uidvalidity","message_id","received_at","from_name","from_email","recipient_to","cc","reply_to","subject","attachments","attachment_count","amea_numbers","h_project_numbers","sam_numbers","direction","fetched_at_utc","in_reply_to","references","migration_state","owner_verification","invoice_numbers"]
def call(s,method,endpoint,**kw):
    r=s.request(method,"https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+endpoint,timeout=90,**kw)
    r.raise_for_status()
    return r.json() if r.content else {}
def read(s,tab,area):
    return call(s,"GET","/values/"+urllib.parse.quote("'"+tab+"'!"+area,safe="")).get("values",[])
def from_legacy(r,i):
    uid=get(r,0)
    return [legacy_key(r,i),"All Emails",i,uid,"","","",get(r,1),get(r,2),get(r,3),get(r,4),get(r,5),get(r,6),get(r,7),get(r,8),get(r,9),get(r,10),get(r,11),get(r,12),get(r,13),"OUTBOUND" if uid.upper().startswith("SENT:") else "INBOUND","","","","LEGACY_IDENTITY_UNVERIFIED","",""]
def from_staging(r,i):
    return [staging_key(r),"CSS Git Ingest",i,"",get(r,3),get(r,2),get(r,4),get(r,1),get(r,5),"",get(r,6),get(r,7),get(r,8),"",get(r,9),"","",get(r,10),get(r,11),get(r,12),get(r,15),get(r,14),get(r,16),get(r,17),"STAGING_ATTACHMENTS_UNAVAILABLE","",""]
def main():
    if os.getenv("CANONICAL_SHADOW_WRITE")!="true":raise RuntimeError("EXPLICIT_OPT_IN_REQUIRED")
    cred=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    s=AuthorizedSession(cred)
    legacy=read(s,"All Emails","A1:N50000")
    stage=read(s,"CSS Git Ingest","A1:R50000")
    result=plan(legacy,stage)
    target=read(s,TAB,"A1:A60000")
    if not target or target[0]!=[COLS[0]]:raise RuntimeError("CANONICAL_HEADER_MISSING")
    saved=[r[0] for r in target[1:] if r and r[0]]
    if len(saved)!=len(set(saved)):raise RuntimeError("CANONICAL_DUPLICATES")
    existing=set(saved)
    candidates=(from_legacy(r,i) for i,r in enumerate(legacy[1:],2) if get(r,0))
    recent=(from_staging(r,i) for i,r in enumerate(stage[1:],2) if get(r,0))
    # Process every unsaved source row in one invocation; each request stays bounded.
    pending=[]
    for row in list(candidates)+list(recent):
        if row[0] not in existing:pending.append(row)

    print("CANONICAL_SHADOW_PLAN "+json.dumps({"legacy":result["legacy_rows"],"staging":result["staging_rows"],"saved":len(saved),"to_append":len(pending),"cutover":False}))
    if pending:
        path="/values/"+urllib.parse.quote("'"+TAB+"'!A:AA",safe="")+":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
        for i in range(0,len(pending),250):
            call(s,"POST",path,json={"values":pending[i:i+250]})
            if i%2500==0:print("CANONICAL_SHADOW_PROGRESS "+str(min(i+250,len(pending)))+"/"+str(len(pending)),flush=True)
    after=read(s,TAB,"A1:A60000")
    keys=[r[0] for r in after[1:] if r and r[0]]
    expected=existing | {r[0] for r in pending}
    if len(keys)!=len(expected) or set(keys)!=expected:raise RuntimeError("SHADOW_KEY_PARITY_FAILED")
    print("CANONICAL_SHADOW_CHECKPOINT "+json.dumps({"saved":len(keys),"new":len(keys)-len(saved),"total_source_rows":result["canonical_staging_rows_before_dedupe"],"cutover_allowed":False}))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CANONICAL_SHADOW_FAILED "+type(e).__name__+":"+str(e)[:140],file=sys.stderr);sys.exit(1)
