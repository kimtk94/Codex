#!/usr/bin/env python3
"""SFDC Opportunity and Quotation mirror via existing Google Sheets. No Salesforce API."""
import datetime as dt
import json
import os
import sys
import urllib.parse
from followup_stage1 import auth, call, SOURCE_ID, OUTPUT_ID

SFDC_AUTO_ID = os.getenv("SFDC_AUTO_SHEET_ID", "11Kb6V-y5BYqHdbxZ_X3ZmOxsIFEk683yqELVjafcCac")
KST = dt.timezone(dt.timedelta(hours=9))
JOBS = [
    ("Opportunity", SFDC_AUTO_ID, "Oppo list", 2000),
    ("Quotation", SFDC_AUTO_ID, "Quotation", 2000),
    ("SFDC Contacts", SFDC_AUTO_ID, "Contact", 2000),
    ("SFDC Settlement Raw", SFDC_AUTO_ID, "Setteled_Rawdata", 2000),
    ("SFDC Invoice Index", SFDC_AUTO_ID, "Issued Invoice", 2000),
    ("Quotation Approvals", SOURCE_ID, "Quotation Approval List", 2000),
    ("Quotation Invoice Match", SOURCE_ID, "Quotation Invoice Match", 2000),
]

def range_data(session, source_id, tab, maxrows):
    q=urllib.parse.quote("'%s'!A1:AZ%d" % (tab.replace("'","''"), maxrows), safe="")
    return call(session,"GET","https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (source_id,q),
                stage="mirror_read:"+tab).get("values",[])

def ensure_tabs(session):
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    metadata=call(session,"GET",root+"?fields=sheets.properties",stage="mirror_metadata")
    existing={s["properties"]["title"] for s in metadata.get("sheets",[])}
    todo=[{"addSheet":{"properties":{"title":tab}}} for tab,*_ in JOBS if tab not in existing]
    if todo:
        call(session,"POST",root+":batchUpdate",json={"requests":todo},stage="mirror_create_tabs")

def replace_tab(session, tab, values):
    base="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID+"/values/"
    clear_range=urllib.parse.quote("'%s'!A:AZ" % tab,safe="")
    call(session,"POST",base+clear_range+":clear",json={},stage="mirror_clear:"+tab)
    if values:
        encoded=urllib.parse.quote("'%s'!A1" % tab,safe="")
        call(session,"PUT",base+encoded+"?valueInputOption=RAW",
             json={"majorDimension":"ROWS","values":values},stage="mirror_write:"+tab)

def main():
    session=auth()
    ensure_tabs(session)
    summary={}
    for tab,source_id,source_tab,maxrows in JOBS:
        try:
            rows=range_data(session,source_id,source_tab,maxrows)
        except RuntimeError as exc:
            # A missing SFDC_Auto share must never erase the last successful snapshot.
            summary[tab]={"status":"blocked","error":str(exc)}
            continue
        # Empty reads do not destroy last good data.
        if not rows:
            summary[tab]={"status":"empty_source_preserved"}
            continue
        replace_tab(session,tab,rows)
        summary[tab]={"status":"ok","records":max(0,len(rows)-1)}
    print(json.dumps({"status":"complete","sheets":summary,"checked_at":dt.datetime.now(KST).isoformat()},ensure_ascii=False))
    if summary["Opportunity"]["status"]!="ok" or summary["Quotation"]["status"]!="ok":
        print("NOTICE: SFDC_Auto needs Viewer sharing with the CKD service account.",file=sys.stderr)

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("SFDC mirror failed: %s" % (str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
