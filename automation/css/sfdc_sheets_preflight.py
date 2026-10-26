#!/usr/bin/env python3
"""Fail-fast Google Sheets access test without exposing secret material or customer data."""
import os, json, base64, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("Google service-account secret is missing")
    try: key=json.loads(raw)
    except ValueError:key=json.loads(base64.b64decode(raw))
    required={"client_email","private_key","token_uri"}
    if not required.issubset(key):raise RuntimeError("Secret is not a service-account JSON key")
    credential=service_account.Credentials.from_service_account_info(
        key,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets=build("sheets","v4",credentials=credential,cache_discovery=False).spreadsheets()
    for label,env,tab in [
        ("SFDC","SFDC_SHEET_ID","Email Review Decisions"),
        ("QQ","CSS_SHEET_ID","BI Mail Review & Exclusions"),
    ]:
        book=os.environ[env]
        try:
            response=sheets.values().get(spreadsheetId=book,range="'"+tab+"'!A1",
                valueRenderOption="FORMATTED_VALUE").execute()
            if not response.get("values"):raise RuntimeError("Expected worksheet header is empty")
        except Exception as exc:
            raise RuntimeError(label+" sheet access failed: "+type(exc).__name__) from None
        print(label+"_SHEETS_READ=PASS")
    print("GOOGLE_AUTH_AND_BOTH_SHEETS_READ=PASS")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(type(e).__name__+": "+str(e),file=sys.stderr)
        sys.exit(1)
