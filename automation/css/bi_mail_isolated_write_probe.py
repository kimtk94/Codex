#!/usr/bin/env python3
"""Probe Google Sheets write permission in an ephemeral tab only.

No mail records or exclusion ledgers are modified. The temporary sheet is removed
in a finally block, including when verification raises.
"""
import json
import os
import secrets
from google.oauth2 import service_account
from googleapiclient.discovery import build

BOOK=os.environ["CSS_SHEET_ID"]
SCOPES=["https://www.googleapis.com/auth/spreadsheets"]
def main():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
    if not raw:
        raise RuntimeError("Missing service account secret")
    creds=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=SCOPES)
    api=build("sheets","v4",credentials=creds,cache_discovery=False).spreadsheets()
    title="_BI_SYNC_WRITE_PROBE_"+secrets.token_hex(5)
    created=None
    try:
        result=api.batchUpdate(spreadsheetId=BOOK,body={"requests":[{"addSheet":{"properties":{"title":title,"gridProperties":{"rowCount":2,"columnCount":2}}}}]}).execute()
        created=result["replies"][0]["addSheet"]["properties"]["sheetId"]
        api.values().update(spreadsheetId=BOOK,range="'"+title+"'!A1",valueInputOption="RAW",body={"values":[["WRITE_PROBE_PASS"]]}).execute()
        read=api.values().get(spreadsheetId=BOOK,range="'"+title+"'!A1").execute()
        assert read.get("values")==[["WRITE_PROBE_PASS"]], "Probe verification failed"
        print(json.dumps({"isolated_write_probe":"PASS","cleanup":"attempted"},ensure_ascii=False))
    finally:
        if created is not None:
            api.batchUpdate(spreadsheetId=BOOK,body={"requests":[{"deleteSheet":{"sheetId":created}}]}).execute()
if __name__=="__main__":
    main()
