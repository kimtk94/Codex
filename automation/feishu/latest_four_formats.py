#!/usr/bin/env python3
"""Read-only latest-sheet selection across four recurring dated formats."""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from sheets_tab_discovery import api, TOKEN

DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-._/ ]?(0?[1-9]|1[0-2])[-._/ ]?(0?[1-9]|[12]\d|3[01])(?!\d)")
def parse(title):
    matches=[]
    for m in DATE_RE.finditer(title):
        try:
            day=dt.date(int(m[1]),int(m[2]),int(m[3]))
            matches.append((m.start(),m.end(),day))
        except ValueError:
            continue
    if len(matches)!=1:
        return None
    a,b,day=matches[0]
    base=re.sub(r"[^\w]+","",title[:a]+title[b:]).casefold()
    return (base,day) if base else None

def main():
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    path="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+"/sheets/query"
    sheets=api(path,auth["tenant_access_token"]).get("sheets")
    if not isinstance(sheets,list): raise RuntimeError("No worksheet list")
    groups=defaultdict(list)
    unmatched=0
    for item in sheets:
        sid=item.get("sheet_id")
        title=item.get("title")
        if not sid or not isinstance(title,str):
            raise RuntimeError("Missing worksheet identifier or title")
        parsed=parse(title)
        if parsed is None:
            unmatched+=1
            continue
        key,day=parsed
        groups[key].append((day,sid))
    print("SHEET_COUNT:",len(sheets))
    print("DATED_FORMAT_COUNT:",len(groups))
    print("UNCLASSIFIED_SHEET_COUNT:",unmatched)
    if len(groups)!=4:
        print("LATEST_SELECTION: BLOCKED_EXPECTED_FOUR_FORMATS")
        print("WRITE_OPERATIONS: 0")
        return 2
    for key,rows in sorted(groups.items()):
        newest=max(d for d,_ in rows)
        winners=[sid for day,sid in rows if day==newest]
        if len(winners)!=1:
            raise RuntimeError("Latest-date tie within format")
        # Hash the normalized format; do not emit source worksheet titles.
        digest=hashlib.sha256(key.encode()).hexdigest()[:12]
        print("FORMAT:",digest,"LATEST_DATE:",newest.isoformat(),"SHEET_ID:",winners[0],"VERSIONS:",len(rows))
    print("LATEST_SELECTION: PASS")
    print("SYNC_MODE: DRY_RUN")
    print("BASE_TABLE_CREATION: DISABLED")
    print("WRITE_OPERATIONS: 0")
    return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc:
        print("LATEST_SELECTION_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
