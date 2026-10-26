#!/usr/bin/env python3
"""Write sanitized SFDC email sync health to the SFDC Automation Health tab."""
import os,json,base64,datetime,sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("Missing service-account credentials")
    try:key=json.loads(raw)
    except ValueError:key=json.loads(base64.b64decode(raw))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        key,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
    status=os.getenv("SYNC_JOB_STATUS","UNVERIFIED").upper()
    if status not in {"PASS","FAILURE","UNVERIFIED"}:raise ValueError("Invalid sync status")
    rows=api.get(spreadsheetId=SFDC,range="'Email Review Decisions'!A2:N1300",
                 valueRenderOption="FORMATTED_VALUE").execute().get("values",[])
    pending=sum(1 for r in rows if len(r)>13 and str(r[13]).startswith("PENDING"))
    synced=sum(1 for r in rows if len(r)>13 and str(r[13])=="SYNCED")
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    # Row 8 reserved for this workflow. Do not imply the last success on a failed run.
    old=api.get(spreadsheetId=SFDC,range="'Automation Health'!A8:D8").execute().get("values",[])
    last=now if status=="PASS" else (old[0][1] if old and len(old[0])>1 else "")
    detail="pending="+str(pending)+" synced="+str(synced)+" run="+os.getenv("GITHUB_RUN_ID","unknown")
    api.update(spreadsheetId=SFDC,range="'Automation Health'!A8:D8",
        valueInputOption="RAW",body={"values":[["SFDC Email Decision Sync",last,status,detail]]}).execute()
    print(json.dumps({"state":status,"pending":pending,"synced":synced}))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(type(e).__name__+": "+str(e),file=sys.stderr)
        sys.exit(1)
