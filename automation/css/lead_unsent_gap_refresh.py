#!/usr/bin/env python3
"""Safely refresh all no-sent-evidence Leads after SFDC 3-report staging.

Legacy Lead IDs and decisions remain untouched. A mail match means exact
recipient + authorized sender + OUTBOUND + sent on/after Lead creation.
NO_SENT_EVIDENCE means no qualifying QQ record, not proof of no phone contact.
"""
import base64
import datetime as dt
import json
import os
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build

DST = os.getenv("SFDC_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
SRC = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
KST = dt.timezone(dt.timedelta(hours=9))
SENDERS = {"taehoon.kim@novogene.com", "masiyuan8900@novogene.com",
           "jiin.yoo@novogene.com"}
ADDR = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
AUDIT_HEAD = ["Lead ID","Created","Institution","Name","Email","Inquiry Preview",
              "Sent Evidence","Sent Count","Last Outbound (KST)","Source",
              "Review Action","Audit Date"]
FOCUS_HEAD = ["Priority","Cohort","Lead ID","Institution","Name","Email",
              "Inquiry Preview","Due / Created","Mail Evidence",
              "Last Outbound (KST)","Next Action","Snapshot KST"]
ALL_HEAD = ["Lead ID","Cohort","Created Date","Institution","Name","Email",
            "Inquiry Description","Lead Status","Opportunity ID","Action Class",
            "Outbound Evidence","Review Note","Snapshot KST"]
TARGETS = [("SFDC New Lead Email Audit",150,AUDIT_HEAD),
           ("Lead Unsent Review",250,FOCUS_HEAD),
           ("Lead No-Sent All",350,ALL_HEAD)]


def value(row, i):
    return str(row[i]).strip() if i < len(row) and row[i] is not None else ""


def parse_time(text):
    try:
        d = dt.datetime.fromisoformat(str(text or "").replace("Z", "+00:00"))
        return d.astimezone(KST) if d.tzinfo else d.replace(tzinfo=KST)
    except ValueError:
        return None


def lead_date(text):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=KST)
        except (ValueError, TypeError):
            pass
    return None


def clean(text, n=190):
    return " ".join(str(text or "").split())[:n]


def build_rows(raw, legacy, priority, mail, flags, now):
    if not raw or "SFDC Lead ID" not in raw[0] or "Email" not in raw[0]:
        raise ValueError("Fresh Lead report is missing stable ID/email")
    if not legacy or value(legacy[0],0)!="Lead ID" or len(legacy[0]) < 30:
        raise ValueError("Legacy Lead Followup schema mismatch")
    if not priority or value(priority[0],0)!="Lead ID":
        raise ValueError("Lead Action Priority schema mismatch")
    if not mail or mail[0][:3] != ["received_at","from_email","recipient_to"]:
        raise ValueError("QQ sent evidence schema mismatch")
    if not flags or value(flags[0],0)!="direction":
        raise ValueError("QQ sent direction schema mismatch")
    if len(mail) != len(flags):
        raise ValueError("QQ sent source is not row-aligned")
    ix = {h:i for i,h in enumerate(raw[0])}
    old = {value(r,0):r for r in legacy[1:] if value(r,0)}
    if len(old) != len([r for r in legacy[1:] if value(r,0)]):
        raise ValueError("Duplicate legacy Lead ID")
    current = [r for r in raw[1:] if value(r,ix["SFDC Lead ID"])]
    if len(current) != len({value(r,ix["SFDC Lead ID"]) for r in current}):
        raise ValueError("Duplicate fresh Lead ID")
    if len(current) < len(old):
        raise ValueError("Fresh Lead report is smaller than legacy evidence")
    stage_dates = [parse_time(value(r,0)) for r in mail[1:]]
    stage_dates = [x for x in stage_dates if x]
    if not stage_dates or now-max(stage_dates) > dt.timedelta(hours=48):
        raise ValueError("QQ outbound coverage stale; refuse no-sent classification")
    if max(stage_dates)-now > dt.timedelta(hours=12):
        raise ValueError("Future-dated QQ evidence; refuse classification")
    stage_first = min(stage_dates)
    sent_by_email = {}
    for i in range(1,len(mail)):
        if value(flags[i],0).upper() != "OUTBOUND":
            continue
        row = mail[i]
        if value(row,1).lower() not in SENDERS:
            continue
        at = parse_time(value(row,0))
        if not at:
            continue
        for address in set(x.lower() for x in ADDR.findall(value(row,2))):
            sent_by_email.setdefault(address,[]).append(at)
    def sent_since(email, created):
        return sorted(x for x in sent_by_email.get(email.lower(),[]) if x>=created)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S KST")
    new_audit = []
    new_unsent = []
    for r in current:
        lid=value(r,ix["SFDC Lead ID"])
        if lid in old:
            continue
        email=value(r,ix["Email"]).lower()
        created=lead_date(value(r,ix["Created Date"]))
        observed = sent_since(email,created) if email and created else []
        complete=bool(email and created and created>=stage_first)
        state=("SENT_CONFIRMED" if observed else
               "NO_SENT_EVIDENCE" if complete else "SOURCE_COVERAGE_UNVERIFIED")
        name=" ".join(v for v in (value(r,ix.get("First Name",999)),
                                   value(r,ix.get("Last Name",999))) if v)
        desc=clean(value(r,ix.get("Description",999)))
        out=[lid,value(r,ix["Created Date"]),value(r,ix["Company / Account"]),
             name,email,desc,state,len(observed),
             observed[-1].isoformat(timespec="seconds") if observed else "",
             "SFDC Email Leads Raw + QQ CSS Git Ingest",
             "Check phone/visit; send first response if none" if state=="NO_SENT_EVIDENCE"
             else "Exclude from unsent" if observed else "Verify source coverage",
             stamp]
        new_audit.append(out)
        if state=="NO_SENT_EVIDENCE" and value(r,ix.get("Lead Status",999)).lower() not in ("converted","unqualified"):
            new_unsent.append(out)
    # Preserve every legacy NO_SENT_EVIDENCE record, including low-information
    # and converted records, in the comprehensive review, but not in the focus queue.
    legacy_unsent=[]
    for r in old.values():
        if value(r,25)!="NO_SENT_EVIDENCE":
            continue
        created=lead_date(value(r,5))
        email=value(r,3).lower()
        # Avoid re-queuing a newly contacted Lead before hourly audit catches up.
        if created and sent_since(email,created):
            continue
        legacy_unsent.append(r)
    eligible={value(r,0):r for r in legacy_unsent}
    focus=[]
    for r in priority[1:]:
        lid=value(r,0)
        if not lid:
            continue
        if lid not in eligible:
            # Hourly source refreshes may race: exclude a newly sent Lead
            # rather than publishing a stale outreach instruction.
            continue
        focus.append([value(r,1) or "P1","EXISTING_AUDITED",lid,value(r,4),
                      value(r,5),value(r,6),clean(value(r,8)),value(r,2),
                      "NO_SENT_EVIDENCE","","Check phone/visit and SFDC Activity",stamp])
    for a in new_unsent:
        focus.append(["P1" if a[5] else "P2","NEW_REPORT_NOT_IN_LEGACY",
                      a[0],a[2],a[3],a[4],a[5],a[1],
                      "NO_SENT_EVIDENCE","","Check other channels; first outreach if none",stamp])
    focus.sort(key=lambda r:(0 if r[1]=="NEW_REPORT_NOT_IN_LEGACY" else 1,
                             0 if r[0]=="P1" else 1,r[7],r[2]))
    focus_ids={x[2] for x in focus}
    full=[]
    for a in new_unsent:
        full.append([a[0],"NEW_REPORT_ONLY",a[1],a[2],a[3],a[4],a[5],
                     "New","", "PRIORITY_OUTREACH" if a[0] in focus_ids else "OTHER_REVIEW",
                     "NO_SENT_EVIDENCE","New report; check other contact channels",stamp])
    for r in legacy_unsent:
        lid=value(r,0)
        category=("PRIORITY_OUTREACH" if lid in focus_ids else
                  "CONVERTED_MANAGE_OPP" if value(r,13)=="CONVERTED" else
                  "LOW_INFO_REVIEW" if value(r,17)=="NO_DESCRIPTION" else "OTHER_REVIEW")
        full.append([lid,"LEGACY_AUDITED",value(r,5),value(r,4),value(r,2),
                     value(r,3),clean(value(r,18)),value(r,6),value(r,11),
                     category,"NO_SENT_EVIDENCE",
                     "Not proof of no contact: check phone/visit and SFDC Activity",stamp])
    if len({x[0] for x in full})!=len(full) or len({x[2] for x in focus})!=len(focus):
        raise ValueError("Duplicate combined Lead identity")
    if not set(focus_ids).issubset({x[0] for x in full}):
        raise ValueError("Priority queue not contained in comprehensive ledger")
    return new_audit,focus,full,{"reported":len(current),"legacy":len(old),
        "new":len(new_audit),"new_sent":sum(x[6]=="SENT_CONFIRMED" for x in new_audit),
        "new_no_sent":len(new_unsent),"total_no_sent":len(full),
        "priority":len(focus),"qq_latest":max(stage_dates).isoformat()}


def main():
    encoded=os.getenv("NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    if not encoded:
        raise RuntimeError("Missing NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        data=json.loads(encoded)
    except ValueError:
        data=json.loads(base64.b64decode(encoded))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        data,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets()
    names=["'SFDC Email Leads Raw'!A1:W700",
           "'Lead Email Followup'!A1:AD700","'Lead Action Priority'!A1:O600"]
    source=api.values().batchGet(spreadsheetId=DST,ranges=names).execute()["valueRanges"]
    qq=api.values().batchGet(spreadsheetId=SRC,
        ranges=["'CSS Git Ingest'!F1:H100000","'CSS Git Ingest'!P1:P100000"]).execute()["valueRanges"]
    if len(source)!=3 or len(qq)!=2:
        raise ValueError("Source batch incomplete; refuse writes")
    datasets=[x.get("values",[]) for x in source+qq]
    audit,focus,full,stats=build_rows(*datasets,dt.datetime.now(KST))
    print("LEAD_NO_SENT_GAP="+json.dumps(stats,ensure_ascii=False),flush=True)
    if os.getenv("LEAD_GAP_APPLY","false").lower()!="true":
        print("LEAD_GAP_DRY_RUN=true",flush=True)
        return
    meta=api.get(spreadsheetId=DST,fields="sheets.properties(title,gridProperties.rowCount)").execute()
    grids={x["properties"]["title"]:x["properties"]["gridProperties"]["rowCount"] for x in meta["sheets"]}
    matrices=[audit,focus,full]
    updates=[]
    for (tab,min_rows,head),rows in zip(TARGETS,matrices):
        cap=grids.get(tab,0)
        if cap<min_rows or len(rows)+1>cap:
            raise ValueError("Missing/insufficient output grid "+tab+" rows="+str(len(rows)))
        width=len(head)
        if any(len(r)!=width for r in rows):
            raise ValueError("Output schema inconsistent "+tab)
        data=[head]+rows+[[""]*width for _ in range(cap-len(rows)-1)]
        end="L" if width==12 else "M"
        updates.append({"range":"'"+tab+"'!A1:"+end+str(cap),"values":data})
    # Single atomic values.batchUpdate. Never delete existing decisions or Lead IDs.
    api.values().batchUpdate(spreadsheetId=DST,
        body={"valueInputOption":"RAW","data":updates}).execute()
    print("LEAD_GAP_APPLIED=true",flush=True)


if __name__=="__main__":
    main()
