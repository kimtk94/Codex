#!/usr/bin/env python3
"""Acknowledge SFDC decisions only after QQ review records report SYNCED."""
import os, json, base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GCP_SA_KEY") or os.getenv("GOOGLE_CREDENTIALS_JSON")
if not raw:raise RuntimeError("Google credentials unavailable")
try: creds=json.loads(raw)
except ValueError:creds=json.loads(base64.b64decode(raw))
api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(creds,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
def read(book,tab):
    return api.get(spreadsheetId=book,range="'"+tab+"'!A2:J1300",valueRenderOption="UNFORMATTED_VALUE").execute().get("values",[])
def field(row,i):
    return str(row[i]).strip() if i<len(row) and row[i] is not None else ""
qq={field(r,4):r for r in read(QQ,"BI Mail Review & Exclusions") if field(r,4)}
updates=[]
for idx,row in enumerate(read(SFDC,"Email Review Decisions"),start=2):
    uid=field(row,4)
    action=field(row,0).upper()
    if action not in {"EXCLUDE_MAIL","EXCLUDE_SENDER","RESTORE_MAIL","RESTORE_SENDER"}:continue
    original=qq.get(uid)
    expected="SYNCED:"+action
    if original and field(original,0).upper()==action and field(original,7)==expected and field(row,7)!=expected:
        updates.append({"range":"'Email Review Decisions'!H"+str(idx),"values":[[expected]]})
if updates:api.batchUpdate(spreadsheetId=SFDC,body={"valueInputOption":"RAW","data":updates}).execute()
print(json.dumps({"acknowledged":len(updates)},ensure_ascii=False))
