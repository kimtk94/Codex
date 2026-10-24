#!/usr/bin/env python3
"""Predict Online-Project completion month from current stage, remaining calendar-day TAT.
Feishu is read-only; output is a private Google Sheet, never a public CI artifact.
"""
import collections
import datetime as dt
import json
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo
from base_readonly_probe import request, require
from payment_table_audit import list_pages
from project_status_sync import google, api, sheet, values

SOURCE = "Online-Project"
DEST = "Feishu Project TAT Forecast"
SUMMARY = "Feishu TAT Monthly"
KST = ZoneInfo("Asia/Seoul")
# Conservative remaining calendar-day assumptions, used only when source TAT absent.
STAGES = {
    "Extraction": (30, "ESTIMATED"),
    "Sample QC": (28, "ESTIMATED"),
    "Lib prep": (21, "ESTIMATED"),
    "Lib QC": (18, "ESTIMATED"),
    "Waiting Sequencing": (14, "ESTIMATED"),
    "Sequencing": (12, "ESTIMATED"),
    "Add-seq": (14, "ESTIMATED"),
    "Demultiplexing": (7, "ESTIMATED"),
    "Data QC": (6, "ESTIMATED"),
    "BI Analysis": (7, "ESTIMATED"),
    "Project Completed": (0, "COMPLETED"),
    "Waiting for Settlement": (0, "DELIVERED_SETTLEMENT_PENDING"),
    "Settled": (0, "SETTLED"),
}
BLOCKED = {
    "Awaiting Feedback(Project Start)": "AWAITING_START",
    "Awaiting Feedback(BI form)": "AWAITING_CUSTOMER",
    "Resending Sample": "RESEND_PENDING",
    "resend samples": "RESEND_PENDING",
    "Waiting PO/payment": "PO_PAYMENT_PENDING",
    "Abnormal": "ABNORMAL_REVIEW",
}
HEAD = ["Snapshot KST","Sub-Project Number","Contract Number","Contract Name",
        "Project Status","Staging Number","Staging Name","Source Remaining TAT Days",
        "Applied Remaining TAT Days","TAT Basis","Forecast Completion Date",
        "Forecast Completion Month","Forecast Category","Source Planned Settled Month",
        "Source Planned USD Excl Tax","Projected KRW @1500","Projected K USD",
        "Difference vs Source Month","Next Action"]
SUMHEAD = ["Completion Month","Total Projects","Total KRW @1500","Total K USD",
           "Source TAT Count","Stage Estimate Count","Completed-status Count",
           "Completed-status Projects","Forecast Projects","Completed-status KRW @1500",
           "Forecast KRW @1500","Completed-status K USD","Forecast K USD"]
FX=1500.0

def textval(x):
    if isinstance(x,list):
        return " ".join(textval(y) for y in x)
    if isinstance(x,dict):
        return str(x.get("text") or x.get("name") or x.get("value") or "")
    return str(x) if x is not None else ""

def numeric(x):
    try:
        if x is None or x=="":return None
        n=float(x)
        return n if 0 <= n < 3660 else None
    except (ValueError,TypeError):return None

def dateval(x):
    if isinstance(x,(float,int)):
        try:return dt.datetime.fromtimestamp(x/1000 if x>1e11 else x, KST).date().isoformat()
        except (OverflowError,OSError,ValueError):return ""
    s=textval(x).strip()
    try:return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:return ""

def add_days(today,n):
    return today+dt.timedelta(days=int(n+0.9999))

def plan(fields,today):
    state=textval(fields.get("Project Status")).strip()
    supplied=numeric(fields.get("Remaining Lead Time-Calendar Days"))
    source_month=dateval(fields.get("Planning Settled Month"))[:7]
    # Blocked states must never count as assured revenue/completion regardless of stale TAT.
    if state in BLOCKED:
        return None,None,"BLOCKED_"+BLOCKED[state],"EXCLUDED",source_month,"Resolve "+state
    if state in ("Project Completed","Waiting for Settlement","Settled"):
        kind=STAGES[state][1]
        return 0,today,kind,"COMPLETED",source_month,"Confirm settlement separately" if state!="Settled" else "Archive"
    if supplied is not None:
        d=add_days(today,supplied)
        return supplied,d,"SOURCE_REMAINING_TAT","FORECAST",source_month,"Verify stage and delivery"
    if state in STAGES:
        days,_=STAGES[state]
        return days,add_days(today,days),"STAGE_ESTIMATE","FORECAST",source_month,"Review TAT fallback"
    return None,None,"UNMAPPED_STAGE","EXCLUDED",source_month,"Map stage and confirm TAT"

def main():
    now=dt.datetime.now(KST)
    today=now.date()
    auth=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
                 body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    if auth.get("code")!=0 or not auth.get("tenant_access_token"):raise RuntimeError("FEISHU_AUTH_FAILED")
    token=auth["tenant_access_token"]
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(require("FEISHU_BASE_APP_TOKEN"),safe="")
    tables=list(list_pages(prefix+"/tables",token))
    matches=[x for x in tables if x.get("name")==SOURCE]
    if len(matches)!=1:raise RuntimeError("ONLINE_PROJECT_MISSING_OR_AMBIGUOUS")
    root=prefix+"/tables/"+urllib.parse.quote(matches[0]["table_id"],safe="")
    fields=list(list_pages(root+"/fields",token))
    available={x.get("field_name") for x in fields}
    if not {"Sub-Project Number","Project Status","Remaining Lead Time-Calendar Days"}.issubset(available):
        raise RuntimeError("REQUIRED_FIELDS_MISSING")
    records=list(list_pages(root+"/records",token))
    if not records:raise RuntimeError("SOURCE_EMPTY_REFUSE_OVERWRITE")
    ids=[x.get("record_id") for x in records]
    if not all(ids) or len(ids)!=len(set(ids)):raise RuntimeError("RECORD_ID_INTEGRITY")
    output=[HEAD]
    monthly=collections.defaultdict(lambda:{"n":0,"usd":0.0,"source":0,"stage":0,"done":0,"done_usd":0.0,"forecast_usd":0.0})
    categories=collections.Counter()
    for record in records:
        fields=record.get("fields") or {}
        days,completion,basis,category,source_month,action=plan(fields,today)
        key=textval(fields.get("Sub-Project Number"))
        if not key: key="REVIEW_RECORD_"+str(len(output))
        month=completion.strftime("%Y-%m") if completion else ""
        usd=numeric(fields.get("Planning Settled Amount Excluding Tax in USD"))
        # Amount is NOT a booked invoice; no amounts on unresolved/blocking records.
        usd_amount=usd if category in ("FORECAST","COMPLETED") else None
        source_date=dateval(fields.get("Planning Settled Month"))
        divergence="YES" if month and source_month and month!=source_month else ("NO" if month and source_month else "UNKNOWN")
        output.append([now.strftime("%Y-%m-%d %H:%M:%S"),key,
            textval(fields.get("Contract Number")),textval(fields.get("Contract Name")),
            textval(fields.get("Project Status")),textval(fields.get("Staging Number")),
            textval(fields.get("Staging Name")),
            numeric(fields.get("Remaining Lead Time-Calendar Days")) or 0 if numeric(fields.get("Remaining Lead Time-Calendar Days")) is not None else "",
            days if days is not None else "",basis,completion.isoformat() if completion else "",
            month,category,source_date,usd_amount if usd_amount is not None else "",
            round(usd_amount*FX) if usd_amount is not None else "",
            round(usd_amount/1000,3) if usd_amount is not None else "",divergence,action])
        categories[basis]+=1
        if month and category in ("FORECAST","COMPLETED"):
            item=monthly[month];item["n"]+=1
            item["usd"]+=usd_amount or 0
            item["source"]+=basis=="SOURCE_REMAINING_TAT"
            item["stage"]+=basis=="STAGE_ESTIMATE"
            item["done"]+=category=="COMPLETED"
            if category=="COMPLETED":item["done_usd"]+=usd_amount or 0
            else:item["forecast_usd"]+=usd_amount or 0
    sums=[SUMHEAD]
    for month,v in sorted(monthly.items()):
        sums.append([month,v["n"],round(v["usd"]*FX),round(v["usd"]/1000,3),
                     v["source"],v["stage"],v["done"],v["done"],v["n"]-v["done"],
                     round(v["done_usd"]*FX),round(v["forecast_usd"]*FX),
                     round(v["done_usd"]/1000,3),round(v["forecast_usd"]/1000,3)])
    session=google()
    sheet(session,DEST);sheet(session,SUMMARY)
    meta=api(session,"GET","?fields=sheets.properties")
    resize=[]
    for tab in meta.get("sheets",[]):
        props=tab.get("properties") or {}
        needed=20 if props.get("title")==DEST else 14 if props.get("title")==SUMMARY else None
        if needed and (props.get("gridProperties") or {}).get("columnCount",0)<needed:
            resize.append({"updateSheetProperties":{"properties":{"sheetId":props["sheetId"],"gridProperties":{"columnCount":needed}},"fields":"gridProperties.columnCount"}})
    if resize:api(session,"POST",":batchUpdate",json={"requests":resize})
    # Replace generated destination tabs only; other source/history tabs remain untouched.
    for title in (DEST,SUMMARY):
        range_name=urllib.parse.quote("'"+title+"'!A1:S2000",safe="")
        api(session,"POST","/values/"+range_name+":clear",json={})
    values(session,DEST,"A1",output)
    values(session,SUMMARY,"A1",sums)
    print("TAT_FORECAST_PASS records="+str(len(records))+" months="+str(len(monthly))+
          " stage_source="+str(categories["SOURCE_REMAINING_TAT"])+
          " stage_fallback="+str(categories["STAGE_ESTIMATE"])+
          " blocked="+str(sum(c for k,c in categories.items() if k.startswith("BLOCKED_")))+
          " unmapped="+str(categories["UNMAPPED_STAGE"]))
    print("FEISHU_WRITES: 0; PUBLIC_CUSTOMER_DATA_OUTPUT: 0")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("TAT_FORECAST_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
