#!/usr/bin/env python3
"""Inspect only header shape of newest four Feishu Sheets tabs; never print cell values."""
import datetime as dt
import hashlib
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo
from sheets_tab_discovery import api, TOKEN
from latest_four_formats import select

def main():
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    bearer=auth["tenant_access_token"]
    root="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    sheets=api(root+"/sheets/query",bearer).get("sheets")
    if not isinstance(sheets,list): raise RuntimeError("Sheet listing unavailable")
    selected,unclassified=select(sheets,dt.datetime.now(ZoneInfo("Asia/Seoul")).date())
    if selected is None: raise RuntimeError("Exactly four formats required")
    print("FORMAT_COUNT:",len(selected))
    for fmt,entry in sorted(selected.items()):
        # A1:AZ1 is header-only; structural fingerprints do not disclose names.
        span=urllib.parse.quote(entry["sheet_id"]+"!A1:AZ1",safe="")
        result=api(root+"/values/"+span,bearer)
        values=result.get("valueRange",{}).get("values",[])
        header=values[0] if values else []
        normalized=[str(x).strip().casefold() for x in header]
        if not any(normalized): raise RuntimeError("Empty header for "+fmt)
        if len(set(x for x in normalized if x))!=len([x for x in normalized if x]):
            raise RuntimeError("Duplicate nonempty header in "+fmt)
        fingerprint=hashlib.sha256("\x1f".join(normalized).encode()).hexdigest()[:16]
        print("FORMAT:",fmt,"HEADER_COLUMNS:",len(header),"HEADER_FINGERPRINT:",fingerprint)
    print("SCHEMA_AUDIT: PASS")
    print("CELL_CONTENT_LOGGING: DISABLED")
    print("BASE_WRITES: 0")
if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("SCHEMA_AUDIT_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
