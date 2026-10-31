#!/usr/bin/env python3
"""Independent dated Feishu Sheets eTax source diagnostic, not bank/issuance certification."""
import datetime as dt
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo
from sheets_tab_discovery import api,TOKEN
from latest_four_formats import select

REQUIRED={"ERP Invoice Number","CMS Invoice Num","Amount","Project Number","Quotation Number","Sales"}

def classify(selected,today):
    if selected is None or "eTax Invoice" not in selected:
        return "BLOCK_MISSING_DATED_SHEET",None
    item=selected["eTax Invoice"]
    try:d=dt.date.fromisoformat(item["date"])
    except (KeyError,ValueError,TypeError):return "BLOCK_BAD_SOURCE_DATE",None
    if (d.year,d.month)!=(today.year,today.month) or d>today:
        return "BLOCK_WRONG_MONTH",d
    return ("CURRENT_MONTH_SNAPSHOT_FRESH" if (today-d).days<=2
            else "CURRENT_MONTH_SNAPSHOT_STALE_REVIEW"),d

def headers_ok(rows):
    if not isinstance(rows,list):return False
    for row in rows[:5]:
        if not isinstance(row,list):continue
        if REQUIRED.issubset({str(x).strip() for x in row}):return True
    return False

def main():
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],
        "app_secret":os.environ["FEISHU_APP_SECRET"]})
    bearer=auth["tenant_access_token"]
    prefix="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    tabs=api(prefix+"/sheets/query",bearer).get("sheets")
    if not isinstance(tabs,list):raise RuntimeError("FEISHU_DATED_SHEETS_MISSING")
    today=dt.datetime.now(ZoneInfo("Asia/Seoul")).date()
    selected,_=select(tabs,today)
    result,source=classify(selected,today)
    print("ETAX_DATED_SHEET_STATUS:",result)
    print("ETAX_DATED_TARGET_MONTH:",today.strftime("%Y-%m"))
    print("ETAX_DATED_SOURCE_DATE:",source.isoformat() if source else "UNKNOWN")
    if source is None or result.startswith("BLOCK_"):return 2
    item=selected["eTax Invoice"]
    sid=item["sheet_id"]
    # Schema-only read: never log customer values, record IDs, or receipt amounts.
    path=("/open-apis/sheets/v2/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")+
        "/values/"+urllib.parse.quote(sid+"!A1:AC5",safe="!:"))
    body=api(path,bearer)
    rows=(body.get("valueRange") or {}).get("values")
    valid=headers_ok(rows)
    print("ETAX_DATED_REQUIRED_SCHEMA:", "PASS" if valid else "BLOCK")
    print("ETAX_DATED_SOURCE_AGE_DAYS:",(today-source).days)
    print("ETAX_SETTLEMENT_OR_ISSUANCE_CERTIFIED: False")
    print("ETAX_WRITE_OPERATIONS: 0")
    return 0 if valid else 2
if __name__=="__main__":
    try:sys.exit(main())
    except Exception as e:
        print("ETAX_DATED_SOURCE_FAILED="+type(e).__name__,file=sys.stderr)
        sys.exit(1)
