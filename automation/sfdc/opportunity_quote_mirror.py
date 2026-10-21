#!/usr/bin/env python3
"""SFDC Opportunity and Quotation mirror via existing Google Sheets. No Salesforce API."""
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.parse
from followup_stage1 import auth, call, SOURCE_ID, OUTPUT_ID

SFDC_AUTO_ID = os.getenv("SFDC_AUTO_SHEET_ID", "11Kb6V-y5BYqHdbxZ_X3ZmOxsIFEk683yqELVjafcCac")
KST = dt.timezone(dt.timedelta(hours=9))
JOBS = [
    ("SFDC Opportunity Raw", SFDC_AUTO_ID, "Oppo list", 2000),
    ("Quotation", SFDC_AUTO_ID, "Quotation", 2000),
    ("SFDC Contacts", SFDC_AUTO_ID, "Contact", 2000),
    ("SFDC Settlement Raw", SFDC_AUTO_ID, "Setteled_Rawdata", 2000),
    ("SFDC Invoice Index", SFDC_AUTO_ID, "Issued Invoice", 2000),
    ("Quotation Approvals", SOURCE_ID, "Quotation Approval List", 2000),
    ("Quotation Invoice Match", SOURCE_ID, "Quotation Invoice Match", 2000),
    ("CSS Action Center", SOURCE_ID, "CSS Action Center", 2000),
    ("CSS Customer 360", SOURCE_ID, "CSS Customer 360", 2000),
    ("CSS Project Timeline", SOURCE_ID, "CSS Project Timeline", 6000),
    ("CSS Contract-SIF", SOURCE_ID, "CSS Contract-SIF Tracker", 2000),
    ("CSS Review Queue", SOURCE_ID, "CSS Review Queue", 2000),
    ("CSS Manual Issues", SOURCE_ID, "CSS Manual Issues", 2000),
    ("CSS Tax Invoices", SOURCE_ID, "CSS Tax Invoice List", 2000),
    ("CSS System Health", SOURCE_ID, "CSS System Health", 2000),
]
AUDIT_TAB = "SFDC Source Audit"
READINESS_TAB = "SFDC Report Readiness"
REQUIRED_FIELDS = {"SFDC Opportunity Raw": ["Opportunity ID", "Last Modified Date", "Stage", "Close Date"], "Quotation": ["SFDC Quotation ID", "Quotation ID", "Opportunity Name", "Active", "Last Modified Date"], "SFDC Contacts": ["Contact ID", "Last Modified Date", "Account ID"]}
AUDIT_HEADER = ["source_tab","record_count","first_seen_this_snapshot","last_checked_kst","content_changed","fingerprint_sha256","source_kind","freshness_verified"]

def range_data(session, source_id, tab, maxrows):
    q=urllib.parse.quote("'%s'!A1:AZ%d" % (tab.replace("'","''"), maxrows), safe="")
    return call(session,"GET","https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (source_id,q),
                stage="mirror_read:"+tab).get("values",[])

def ensure_tabs(session):
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    metadata=call(session,"GET",root+"?fields=sheets.properties",stage="mirror_metadata")
    existing={s["properties"]["title"] for s in metadata.get("sheets",[])}
    todo=[{"addSheet":{"properties":{"title":tab}}} for tab in [job[0] for job in JOBS] + [AUDIT_TAB, READINESS_TAB] if tab not in existing]
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
    previous={}
    try:
        prior=range_data(session,OUTPUT_ID,AUDIT_TAB,100)
        previous={row[0]:row for row in prior[1:] if len(row)>=6}
    except RuntimeError:
        pass
    audit=[AUDIT_HEADER]
    readiness=[["object","records","stable_id","modified_timestamp","required_field_check","missing_fields","promotion_status","source"]]
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
        digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
        prior=previous.get(tab,[])
        changed="UNKNOWN" if not prior else ("YES" if prior[5]!=digest else "NO")
        first_seen=dt.datetime.now(KST).isoformat() if changed!="NO" else prior[2]
        audit.append([tab,max(0,len(rows)-1),first_seen,dt.datetime.now(KST).isoformat(),changed,digest,
                      "SFDC_Auto snapshot" if source_id==SFDC_AUTO_ID else "CSS email-derived sheet","NO"])
        if tab in REQUIRED_FIELDS:
            headers={str(h).strip().lower() for h in rows[0]}
            missing=[field for field in REQUIRED_FIELDS[tab] if field.lower() not in headers]
            readiness.append([tab,max(0,len(rows)-1),
                              "NO" if any(" id" in x.lower() for x in missing) else "YES",
                              "NO" if "Last Modified Date" in missing else "YES",
                              "PASS" if not missing else "FAIL",", ".join(missing),
                              "HOLD - report export not verified","SFDC_Auto snapshot"])
        replace_tab(session,tab,rows)
        summary[tab]={"status":"ok","records":max(0,len(rows)-1),"snapshot_changed":changed}
    # Keep the raw opportunity mirror hidden; the enriched visible Opportunity is
    # published only by active_quote_links.py after reconciliation.
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    m=call(session,"GET",root+"?fields=sheets.properties",stage="raw_opportunity_visibility")
    raw=next((v["properties"] for v in m["sheets"] if v["properties"]["title"]=="SFDC Opportunity Raw"),None)
    if raw and not raw.get("hidden"):
        call(session,"POST",root+":batchUpdate",
             json={"requests":[{"updateSheetProperties":{"properties":{"sheetId":raw["sheetId"],"hidden":True},"fields":"hidden"}}]},
             stage="hide_raw_opportunity")
    if len(audit)>1:
        replace_tab(session,AUDIT_TAB,audit)
    if len(readiness)>1:
        replace_tab(session,READINESS_TAB,readiness)
    print(json.dumps({"status":"complete","sheets":summary,"checked_at":dt.datetime.now(KST).isoformat()},ensure_ascii=False))
    if summary["SFDC Opportunity Raw"]["status"]!="ok" or summary["Quotation"]["status"]!="ok":
        print("NOTICE: SFDC_Auto needs Viewer sharing with the CKD service account.",file=sys.stderr)

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("SFDC mirror failed: %s" % (str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
