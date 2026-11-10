#!/usr/bin/env python3
"""Personal QQ sent-mail dates for *every* fresh SFDC Lead, keyed by Lead ID.

Only sends from the owner's exact address count; messages where a lead
is merely copied are counted separately. No mail is sent, no Lead is edited.
"""
import datetime as dt
import json
import os
import re
import sys
from collections import Counter
from google.oauth2 import service_account
from googleapiclient.discovery import build

import lead_my_sent_refresh as source

DEST = os.getenv("SFDC_SHEET_ID",source.DEST)
QQ = os.getenv("CSS_SHEET_ID",source.QQ)
TAB = "Lead Sent Dates"
HEAD = [
    "Lead ID","Institution","Lead Name","Lead Email","Lead Created",
    "Lead Status","Lead Owner","Personal Mail Evidence",
    "Sent After Lead Count","First Sent After Lead (KST)",
    "Last Sent After Lead (KST)","Sent Ever Count",
    "First Sent Ever (KST)","Last Sent Ever (KST)",
    "Direct To Count","CC Copy Count","Latest Message-ID Evidence",
    "Latest QQ Source Checked (KST)","Lead Source Checked (KST)",
    "Suggested Review","Snapshot (KST)",
]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def val(row,i):
    return source.cell(row,i)


def stamp(value):
    return value.isoformat(timespec="seconds") if value else ""


def build_rows(raw, historical, history_dir, staging, stage_dir, now,
               lead_checked=""):
    if not raw or not all(x in raw[0] for x in (
        "SFDC Lead ID","Email","Created Date","Lead Owner",
        "Company / Account","First Name","Last Name","Lead Status"
    )):
        raise RuntimeError("LEAD_REPORT_REQUIRED_COLUMNS_MISSING")
    by_email, latest = source.parse_messages(
        historical,history_dir,staging,stage_dir,now
    )
    ix={name:i for i,name in enumerate(raw[0])}
    ids=set()
    out=[]
    counts=Counter()
    for row in raw[1:]:
        lead_id=val(row,ix["SFDC Lead ID"])
        if not lead_id:continue
        if lead_id in ids:
            raise RuntimeError("DUPLICATE_SFDC_LEAD_ID")
        ids.add(lead_id)
        lead_email=val(row,ix["Email"]).lower()
        created=source.date_of(val(row,ix["Created Date"]))
        if lead_email and source.emails(lead_email) != {lead_email}:
            raise RuntimeError("INVALID_LEAD_EMAIL")
        matches=sorted(by_email.get(lead_email,[]) if lead_email else [],
                       key=lambda x:x["at"])
        after=[item for item in matches if created is not None and item["at"]>=created]
        direct=sum(lead_email in item["to"] for item in after)
        copied=sum(lead_email in item["cc"] and lead_email not in item["to"]
                   for item in after)
        if not lead_email:
            state="LEAD_EMAIL_MISSING"
            action="Verify Lead email address"
        elif created is None:
            state="CREATED_DATE_UNVERIFIED"
            action="Verify Lead created date"
        elif after:
            state="SENT_AFTER_LEAD_CONFIRMED"
            action="Review last sent date / response"
        elif matches:
            state="SENT_BEFORE_LEAD_ONLY"
            action="Check follow-up after Lead creation"
        else:
            state="NO_PERSONAL_OUTBOUND_EVIDENCE"
            action="Verify other channels and QQ coverage"
        counts[state]+=1
        last=matches[-1] if matches else None
        out.append([
            lead_id,val(row,ix["Company / Account"]),
            " ".join(filter(None,[val(row,ix["First Name"]),
                                  val(row,ix["Last Name"])])),
            lead_email,val(row,ix["Created Date"]),val(row,ix["Lead Status"]),
            val(row,ix["Lead Owner"]),state,len(after),
            stamp(after[0]["at"]) if after else "",
            stamp(after[-1]["at"]) if after else "",
            len(matches),stamp(matches[0]["at"]) if matches else "",
            stamp(last["at"]) if last else "",direct,copied,
            val([last["mid"]],0) if last else "",
            stamp(latest),lead_checked,
            action,stamp(now),
        ])
    if len(ids)<450:
        raise RuntimeError("LEAD_SOURCE_UNEXPECTEDLY_SMALL")
    out.sort(key=lambda x:(
        source.date_of(x[4]) or dt.datetime.min.replace(tzinfo=source.KST),
        x[0]
    ),reverse=True)
    return [HEAD]+out,counts,latest


def main():
    raw_key=os.getenv("NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw_key:raise RuntimeError("NBA_GOOGLE_SERVICE_ACCOUNT_JSON_MISSING")
    cfg=json.loads(raw_key)
    credentials=service_account.Credentials.from_service_account_info(cfg,scopes=SCOPES)
    api=build("sheets","v4",credentials=credentials,cache_discovery=False).spreadsheets()
    def meta(book):
        response=api.get(spreadsheetId=book,fields="sheets.properties(title,sheetId,gridProperties)").execute()
        return {x["properties"]["title"]:x["properties"] for x in response.get("sheets",[])}
    def fetch(book,ranges):
        return [r.get("values",[]) for r in api.values().batchGet(
            spreadsheetId=book,ranges=ranges,valueRenderOption="FORMATTED_VALUE"
        ).execute().get("valueRanges",[])]
    sfmeta=meta(DEST)
    qqmeta=meta(QQ)
    requirements=[
        (sfmeta,"SFDC Email Leads Raw"),(sfmeta,"SFDC Email Ingest Audit"),
        (qqmeta,"All Emails"),(qqmeta,"CSS Git Ingest")
    ]
    for available,title in requirements:
        if title not in available:
            raise RuntimeError("MISSING_REQUIRED_SOURCE_TAB_"+title)
    sf=fetch(DEST,[
        "'SFDC Email Leads Raw'!A1:W"+str(sfmeta["SFDC Email Leads Raw"]["gridProperties"]["rowCount"]),
        "'SFDC Email Ingest Audit'!A1:J20",
    ])
    if len(sf)!=2 or not sf[1] or sf[1][0][0]!="Entity":
        raise RuntimeError("SFDC_AUDIT_UNAVAILABLE")
    audit=next((x for x in sf[1][1:] if val(x,0)=="Leads"),None)
    now=dt.datetime.now(source.KST)
    if not audit or not source.verified_lead_stage(audit,now):
        raise RuntimeError("SFDC_LEAD_REPORT_STALE_OR_UNVERIFIED")
    qq=fetch(QQ,[
        "'All Emails'!B1:G"+str(qqmeta["All Emails"]["gridProperties"]["rowCount"]),
        "'All Emails'!U1:U"+str(qqmeta["All Emails"]["gridProperties"]["rowCount"]),
        "'CSS Git Ingest'!B1:I"+str(qqmeta["CSS Git Ingest"]["gridProperties"]["rowCount"]),
        "'CSS Git Ingest'!P1:P"+str(qqmeta["CSS Git Ingest"]["gridProperties"]["rowCount"]),
    ])
    if len(qq)!=4:raise RuntimeError("QQ_SOURCES_INCOMPLETE")
    result,stats,latest=build_rows(sf[0],*qq,now,lead_checked=val(audit,2))
    expected=int(val(audit,3))
    if expected!=len(result)-1:
        raise RuntimeError("LEAD_REPORT_ROW_COUNT_PARITY_FAILED")
    if TAB not in sfmeta:
        api.batchUpdate(spreadsheetId=DEST,body={"requests":[
            {"addSheet":{"properties":{"title":TAB,"gridProperties":{
                "rowCount":max(2000,len(result)+5),"columnCount":24,
                "frozenRowCount":1
            }}}}
        ]}).execute()
        prior=[]
    else:
        props=sfmeta[TAB]
        if props["gridProperties"]["rowCount"]<len(result):
            api.batchUpdate(spreadsheetId=DEST,body={"requests":[
                {"updateSheetProperties":{"properties":{"sheetId":props["sheetId"],
                    "gridProperties":{"rowCount":len(result)+100}},
                    "fields":"gridProperties.rowCount"}}
            ]}).execute()
        prior=fetch(DEST,["'"+TAB+"'!A1:U1"])[0]
        if prior and prior[0]!=HEAD:
            raise RuntimeError("LEAD_SENT_DATES_SCHEMA_CHANGED")
    api.values().update(spreadsheetId=DEST,range="'"+TAB+"'!A1",
        valueInputOption="RAW",body={"values":result}).execute()
    verified=fetch(DEST,[
        "'"+TAB+"'!A1:A"+str(len(result)),
        "'"+TAB+"'!H1:H"+str(len(result)),
    ])
    ids=[val(x,0) for x in verified[0][1:] if val(x,0)]
    statuses=Counter(val(x,0) for x in verified[1][1:] if val(x,0))
    if ids!=[r[0] for r in result[1:]] or statuses!=stats:
        raise RuntimeError("LEAD_SENT_DATES_READBACK_FAILED")
    # Generated-only sheet, no human-entered columns.
    previous_count=sfmeta.get(TAB,{}).get("gridProperties",{}).get("rowCount",0)
    if previous_count>len(result):
        api.values().clear(spreadsheetId=DEST,
            range="'"+TAB+"'!A"+str(len(result)+1)+":U"+str(previous_count),
            body={}).execute()
    print("LEAD_SENT_DATES_PASS "+json.dumps({
        "lead_records":len(ids),"states":stats,"qq_latest":latest.isoformat(),
        "lead_report_checked":val(audit,2),"sender":source.SENDER
    },sort_keys=True))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("LEAD_SENT_DATES_FAILED "+type(exc).__name__+":"+str(exc)[:120],
              file=sys.stderr)
        sys.exit(1)
