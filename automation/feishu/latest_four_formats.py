#!/usr/bin/env python3
"""Read-only latest-of-four selection for recurring Feishu worksheets."""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from zoneinfo import ZoneInfo
from sheets_tab_discovery import api, TOKEN

FORMATS = {
    "Payment Outstanding": re.compile(r"^Payment Outstanding\s+(\d{1,2})\\.(\d{1,2})$", re.I),
    "eTax Invoice": re.compile(r"^eTax\s*-\s*[A-Za-z]+\s+Invoice\s+(\d{1,2})\\.(\d{1,2})$", re.I),
    "Payment Receipt": re.compile(r"^Payment Receipt\s+(\d{1,2})\\.(\d{1,2})$", re.I),
    "Prepayments": re.compile(r"^Prepayments\s+(\d{1,2})\\.(\d{1,2})$", re.I),
}

def classify(title, today):
    matches=[]
    for fmt, pattern in FORMATS.items():
        found=pattern.fullmatch(title.strip())
        if not found:
            continue
        month, day=map(int, found.groups())
        for year in (today.year,today.year-1):
            try:
                date=dt.date(year,month,day)
            except ValueError:
                continue
            if date <= today:
                matches.append((fmt,date))
                break
    if len(matches)>1:
        raise RuntimeError("Ambiguous worksheet format")
    return matches[0] if matches else None

def select(sheets, today):
    grouped=defaultdict(list)
    unclassified=0
    for item in sheets:
        sheet_id=item.get("sheet_id")
        title=item.get("title")
        if not sheet_id or not isinstance(title,str):
            raise RuntimeError("Missing sheet metadata")
        match=classify(title,today)
        if match is None:
            unclassified+=1
        else:
            fmt,date=match
            grouped[fmt].append((date,sheet_id))
    if set(grouped)!=set(FORMATS):
        return None,unclassified
    selected={}
    for fmt,items in grouped.items():
        latest=max(date for date,_ in items)
        winners=[sid for date,sid in items if date==latest]
        if len(winners)!=1:
            raise RuntimeError("Ambiguous newest worksheet")
        selected[fmt]={"date":latest.isoformat(),"sheet_id":winners[0],"versions":len(items)}
    return selected,unclassified

def main():
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    path="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+"/sheets/query"
    sheets=api(path,auth["tenant_access_token"]).get("sheets")
    if not isinstance(sheets,list):
        raise RuntimeError("No worksheet list")
    today=dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    selected,unclassified=select(sheets,today)
    print("SHEET_COUNT:",len(sheets))
    print("UNCLASSIFIED_SHEET_COUNT:",unclassified)
    if selected is None:
        print("LATEST_SELECTION: BLOCKED_EXPECTED_FOUR_FORMATS")
        print("WRITE_OPERATIONS: 0")
        return 2
    for fmt,info in sorted(selected.items()):
        print("FORMAT:",fmt,"LATEST_DATE:",info["date"],"SHEET_ID:",info["sheet_id"],"VERSIONS:",info["versions"])
    print("LATEST_SELECTION: PASS")
    print("SYNC_MODE: DRY_RUN")
    print("BASE_TABLE_CREATION: DISABLED")
    print("WRITE_OPERATIONS: 0")
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("LATEST_SELECTION_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
