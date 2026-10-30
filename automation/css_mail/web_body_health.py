#!/usr/bin/env python3
"""Publish a separate, evidence-limited health row for the derived web body cache.

The QQ IMAP header-ingestion health is independent. A valid body-cache run
does NOT imply full historical mail coverage. No mail, decisions, or source
rows are modified by this monitor.
"""
import datetime as dt
import os
import sys
import time
import urllib.parse

import requests
import incremental_sync as src

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
CACHE="CSS Mail Inbox Raw"
HEALTH="Automation Health"
HEADER=["Component","Last success KST","State","Detail"]
COMPONENT="CSS Mail Body"
KNOWN={"WEB_REVIEW_CACHE","BODY_EMPTY_MIME","HEADER_ONLY_BODY_PENDING"}


def endpoint(sheet, area):
    return ("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+
            "/values/"+urllib.parse.quote("'"+sheet+"'!"+area,safe=""))


def read(session,sheet,area):
    for attempt in range(3):
        try:
            return src.api(session,"GET",endpoint(sheet,area)).get("values",[])
        except (requests.exceptions.Timeout,requests.exceptions.ConnectionError):
            if attempt==2:raise
            time.sleep(1+attempt*2)


def cached_summary(session):
    counts={name:0 for name in KNOWN}
    seen=set()
    rows=0
    chunk=1000
    for start in range(1,10001,chunk):
        end=start+chunk-1
        ids=read(session,CACHE,"A"+str(start)+":A"+str(end))
        statuses=read(session,CACHE,"V"+str(start)+":V"+str(end))
        if start==1:
            if not ids or ids[0]!=["Mail UID"] or not statuses or statuses[0]!=["Classification"]:
                raise RuntimeError("CSS_MAIL_CACHE_SCHEMA_CHANGED")
        for i in range(1 if start==1 else 0,len(ids)):
            uid=ids[i][0].strip() if ids[i] else ""
            if not uid:continue
            if uid in seen:raise RuntimeError("CSS_MAIL_CACHE_UID_DUPLICATE")
            seen.add(uid)
            rows+=1
            state=statuses[i][0].strip() if i<len(statuses) and statuses[i] else ""
            if state not in KNOWN:
                raise RuntimeError("CSS_MAIL_BODY_UNKNOWN_STATUS")
            counts[state]+=1
        if len(ids)<chunk:
            break
    if rows<1:raise RuntimeError("CSS_MAIL_BODY_CACHE_EMPTY")
    if sum(counts.values())!=rows:
        raise RuntimeError("CSS_MAIL_BODY_COUNT_MISMATCH")
    return rows,counts


def health_record(outcome, rows, counts, timestamp):
    ready=counts["WEB_REVIEW_CACHE"]
    empty=counts["BODY_EMPTY_MIME"]
    pending=counts["HEADER_ONLY_BODY_PENDING"]
    stage=("BACKFILL_ACTIVE" if outcome=="success" else "FAIL_BODY_WORKFLOW")
    detail=(f"cached={rows} body_ready={ready} original_no_text={empty} "
            f"header_only={pending} backfill=INCOMPLETE "
            f"previous_action={outcome} QQ_header_health=SEPARATE")
    return [COMPONENT,timestamp,stage,detail]


def publish(session,record):
    data=read(session,HEALTH,"A1:D200")
    if not data or data[0]!=HEADER:
        raise RuntimeError("AUTOMATION_HEALTH_SCHEMA_MISMATCH")
    existing=[i+1 for i,r in enumerate(data) if i>0 and r and r[0]==COMPONENT]
    if len(existing)>1:raise RuntimeError("DUPLICATE_MAIL_BODY_HEALTH_COMPONENT")
    if existing:
        row=existing[0]
        src.api(session,"PUT",endpoint(HEALTH,"A"+str(row)+":D"+str(row))+
                "?valueInputOption=RAW",json={"values":[record]})
    else:
        src.api(session,"POST",endpoint(HEALTH,"A:D")+
                ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
                json={"values":[record]})
    confirm=read(session,HEALTH,"A1:D200")
    observed=[r for r in confirm[1:] if r and r[0]==COMPONENT]
    if len(observed)!=1 or observed[0][:4]!=record:
        raise RuntimeError("MAIL_BODY_HEALTH_WRITE_PARITY_FAILED")


def main():
    outcome=os.getenv("CSS_BODY_STEP_OUTCOME","unknown")
    if outcome not in ("success","failure","skipped","cancelled"):
        raise RuntimeError("INVALID_BODY_STEP_OUTCOME")
    session=src.authorize()
    rows,counts=cached_summary(session)
    stamp=dt.datetime.now(src.KST).strftime("%Y-%m-%d %H:%M:%S KST")
    record=health_record(outcome,rows,counts,stamp)
    publish(session,record)
    print("CSS_MAIL_BODY_HEALTH "+record[2]+" "+record[3],flush=True)
    if outcome!="success":sys.exit(1)


if __name__=="__main__":
    main()
