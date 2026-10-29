#!/usr/bin/env python3
"""Personal QQ sent-mail evidence for SFDC Leads (strict sender + exact To/CC).

Generated: Lead My Sent Audit A:T only. Decision ledgers, approval/choice
columns and CRM are NEVER written. 'No evidence' is not proof of no contact.
"""
import base64
import datetime as dt
import json
import os
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build

DEST = os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ = os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
SENDER = "taehoon.kim@novogene.com"
KST = dt.timezone(dt.timedelta(hours=9))
MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HEADER = ["Lead ID","Created Date","Institution","Customer","Email","Description",
          "Description Class","Lead Status","Opportunity ID","My Sent After Lead",
          "My Sent Before Lead","My Sent Ever","Last Sent After Lead","Last Sent Ever",
          "My Mail Status","QQ Message-ID (Evidence)","To / CC","QQ Source",
          "Latest QQ Outbound Checked","Follow-up Action"]


def cell(row, i):
    return str(row[i]).strip() if i < len(row) and row[i] is not None else ""


def date_of(text):
    if not text:
        return None
    try:
        d = dt.datetime.fromisoformat(str(text).strip().replace("Z","+00:00"))
        return d.astimezone(KST) if d.tzinfo else d.replace(tzinfo=KST)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y","%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    return None


def emails(value):
    return set(x.lower() for x in MAIL.findall(str(value or "")))


def parse_messages(historical, historical_directions, staging, stage_directions, now):
    if not historical or historical[0][:6] != [
            "message_id","received_at","from_name","from_email","to","cc"]:
        raise ValueError("Unexpected QQ All Emails B:G columns")
    if not historical_directions or cell(historical_directions[0],0)!="direction":
        raise ValueError("Unexpected QQ All Emails U direction")
    if not staging or staging[0][:8] != [
            "message_id","imap_uid","folder","uidvalidity","received_at",
            "from_email","recipient_to","cc"]:
        raise ValueError("Unexpected QQ Git Ingest B:I columns")
    if not stage_directions or cell(stage_directions[0],0)!="direction":
        raise ValueError("Unexpected QQ Git Ingest P direction")
    if len(historical)!=len(historical_directions) or len(staging)!=len(stage_directions):
        raise ValueError("QQ source columns not row-aligned")
    stage_times = [date_of(cell(row,4)) for row in staging[1:]]
    stage_times = [t for t in stage_times if t]
    if not stage_times or now-max(stage_times)>dt.timedelta(hours=72):
        raise ValueError("QQ staging coverage stale; refuse to certify no sent")
    if max(stage_times)>now+dt.timedelta(hours=12):
        raise ValueError("QQ staging future dates")
    messages = {}
    def consider(mid, stamp, sender, to, cc, direction, source):
        if str(direction).upper() not in {"SENT","OUTBOUND"}:
            return
        if emails(sender)!={SENDER}:
            return
        when=date_of(stamp)
        if not when:
            return
        to_addrs, cc_addrs=emails(to),emails(cc)
        if not to_addrs and not cc_addrs:
            return
        key=mid.strip().lower() or source+"|"+str(stamp)+"|"+str(to)+"|"+str(cc)
        if key not in messages:
            messages[key]={"at":when,"mid":mid,"to":to_addrs,
                           "cc":cc_addrs,"source":source}
        else:
            prior=messages[key]
            if prior["at"]!=when:
                raise ValueError("Conflicting QQ Message-ID timestamp")
            prior["to"].update(to_addrs)
            prior["cc"].update(cc_addrs)
            if source=="QQ CSS Git Ingest":
                prior["source"]=source
    for i,row in enumerate(historical[1:],1):
        consider(cell(row,0),cell(row,1),cell(row,3),cell(row,4),cell(row,5),
                 cell(historical_directions[i],0),"QQ All Emails")
    for i,row in enumerate(staging[1:],1):
        consider(cell(row,0),cell(row,4),cell(row,5),cell(row,6),cell(row,7),
                 cell(stage_directions[i],0),"QQ CSS Git Ingest")
    by_email={}
    for message in messages.values():
        for address in message["to"]|message["cc"]:
            by_email.setdefault(address,[]).append(message)
    return by_email,max(stage_times)


def build(raw, historical, history_dir, staging, stage_dir, now):
    if not raw or "SFDC Lead ID" not in raw[0] or "Email" not in raw[0]:
        raise ValueError("Latest SFDC Lead report missing required columns")
    ix={name:i for i,name in enumerate(raw[0])}
    required=["SFDC Lead ID","Created Date","First Name","Last Name",
              "Company / Account","Lead Status","Email","Description","Lead Owner"]
    if not all(k in ix for k in required):
        raise ValueError("SFDC Lead schema mismatch")
    by_email, latest=parse_messages(historical,history_dir,staging,stage_dir,now)
    records=[r for r in raw[1:] if cell(r,ix["SFDC Lead ID"])]
    ids=[cell(r,ix["SFDC Lead ID"]) for r in records]
    if len(ids)!=len(set(ids)) or len(records)<450:
        raise ValueError("Lead count/ID integrity failure")
    rows=[]
    for r in records:
        lid=cell(r,ix["SFDC Lead ID"])
        created=date_of(cell(r,ix["Created Date"]))
        email=cell(r,ix["Email"]).lower()
        if not created or not email or len(emails(email))!=1:
            raise ValueError("Missing Lead created date/email: "+lid)
        matches=by_email.get(email,[])
        after=sorted((m for m in matches if m["at"]>=created),key=lambda m:m["at"])
        before=sorted((m for m in matches if m["at"]<created),key=lambda m:m["at"])
        last=after[-1] if after else (before[-1] if before else None)
        desc=cell(r,ix["Description"])
        status=("SENT_AFTER_LEAD_CONFIRMED" if after else
                "SENT_BEFORE_LEAD_ONLY" if before else "NO_PERSONAL_OUTBOUND_EVIDENCE")
        opportunity=cell(r,ix.get("Opportunity ID",999))
        qualified=cell(r,ix["Lead Status"]).upper() in {"QUALIFIED","CONVERTED"} or bool(opportunity)
        action=("ALREADY_CONTACTED" if after else "MANAGE_OPPORTUNITY" if qualified else
                "RECONTACT_LEAD_AFTER_CREATED" if before else
                "CHECK_PHONE_VISIT_THEN_FIRST_EMAIL")
        when=lambda m:m["at"].isoformat(timespec="seconds") if m else ""
        rows.append([lid,created.date().isoformat(),cell(r,ix["Company / Account"]),
                     " ".join(filter(None,(cell(r,ix["First Name"]),cell(r,ix["Last Name"])))),
                     email,desc,"PRESENT" if desc else "MISSING",
                     cell(r,ix["Lead Status"]),opportunity,
                     len(after),len(before),len(matches),when(after[-1] if after else None),
                     when(last),status,cell([last["mid"]],0) if last else "",
                     "TO" if last and email in last["to"] else "CC" if last else "",
                     last["source"] if last else "",when({"at":latest}),
                     action])
    # newest leads first. Stable order on Lead ID for same creation day.
    rows.sort(key=lambda r:(r[1],r[0]),reverse=True)
    by_status={}
    for r in rows:
        by_status[r[14]]=by_status.get(r[14],0)+1
    if sum(by_status.values())!=len(rows):
        raise ValueError("Status accounting failed")
    return [HEADER]+rows,by_status,latest


def main():
    secret=os.getenv("NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:
        raise ValueError("Missing NBA_GOOGLE_SERVICE_ACCOUNT_JSON")
    try:
        cfg=json.loads(secret)
    except ValueError:
        cfg=json.loads(base64.b64decode(secret))
    api=build_service(cfg)
    get=lambda book,ranges: api.values().batchGet(
        spreadsheetId=book,ranges=ranges,valueRenderOption="FORMATTED_VALUE"
    ).execute().get("valueRanges",[])
    def grid(book):
        result=api.get(spreadsheetId=book,
            fields="sheets.properties(title,gridProperties.rowCount)").execute()
        return {x["properties"]["title"]:x["properties"]["gridProperties"]["rowCount"]
                for x in result["sheets"]}
    target_rows=grid(DEST)
    qq_rows=grid(QQ)
    if "SFDC Email Ingest Audit" not in target_rows:
        raise ValueError("SFDC report freshness audit tab missing")
    report_audit=get(DEST,["'SFDC Email Ingest Audit'!A1:J20"])[0].get("values",[])
    lead_audit=next((r for r in report_audit[1:] if cell(r,0)=="Leads"),None)
    if not lead_audit or cell(lead_audit,8)!="STAGED_NOT_PROMOTED":
        raise ValueError("Lead source staging audit missing or unexpected")
    reported_at=date_of(cell(lead_audit,1).removesuffix(" KST"))
    if not reported_at or dt.datetime.now(KST)-reported_at>dt.timedelta(hours=72):
        raise ValueError("Lead source report is stale; refuse to certify no sent")
    for tab,book in (("SFDC Email Leads Raw",target_rows),
                     ("Lead My Sent Audit",target_rows),
                     ("All Emails",qq_rows),("CSS Git Ingest",qq_rows)):
        if book.get(tab,0)<2:
            raise ValueError("Required Google Sheet tab missing: "+tab)
    lead_bound=target_rows["SFDC Email Leads Raw"]
    all_bound=qq_rows["All Emails"]
    stage_bound=qq_rows["CSS Git Ingest"]
    raw=get(DEST,["'SFDC Email Leads Raw'!A1:W"+str(lead_bound)])
    history=get(QQ,["'All Emails'!B1:G"+str(all_bound),
                    "'All Emails'!U1:U"+str(all_bound),
                    "'CSS Git Ingest'!B1:I"+str(stage_bound),
                    "'CSS Git Ingest'!P1:P"+str(stage_bound)])
    if len(raw)!=1 or len(history)!=4:
        raise ValueError("Incomplete SFDC/QQ read")
    source=[x.get("values",[]) for x in raw+history]
    now=dt.datetime.now(KST)
    reported_count=int(cell(lead_audit,3) or 0)
    current_count=sum(bool(cell(r,22)) for r in source[0][1:])
    if current_count!=reported_count:
        raise ValueError("SFDC Leads count differs from source ingest audit")
    matrix,stats,latest=build(*source,now)
    print("PERSONAL_LEAD_AUDIT="+json.dumps({
        "leads":len(matrix)-1,"states":stats,"latest_qq":latest.isoformat()},sort_keys=True),flush=True)
    if os.getenv("LEAD_PERSONAL_APPLY","false").lower()!="true":
        print("PERSONAL_LEAD_AUDIT_DRY_RUN=true")
        return
    sheet="Lead My Sent Audit"
    size=target_rows[sheet]
    if size<len(matrix) or size<650:
        raise ValueError("Personal Audit output grid too small")
    output=matrix+[[""]*len(HEADER) for _ in range(size-len(matrix))]
    api.values().update(spreadsheetId=DEST,range="'"+sheet+"'!A1:T"+str(size),
        valueInputOption="RAW",body={"values":output}).execute()
    verified=get(DEST,["'Lead My Sent Audit'!A1:A"+str(len(matrix)),
                       "'Lead My Sent Audit'!O1:O"+str(len(matrix))])
    if len(verified)!=2:
        raise ValueError("Personal Lead readback missing")
    ids=[cell(r,0) for r in verified[0].get("values",[])[1:] if cell(r,0)]
    states=[cell(r,0) for r in verified[1].get("values",[])[1:] if cell(r,0)]
    check={}
    for state in states:check[state]=check.get(state,0)+1
    if ids!=[r[0] for r in matrix[1:]] or check!=stats:
        raise ValueError("Personal Lead audit readback did not match")
    note=("person="+SENDER+" leads="+str(len(ids))
          +" after="+str(stats.get("SENT_AFTER_LEAD_CONFIRMED",0))
          +" prior_only="+str(stats.get("SENT_BEFORE_LEAD_ONLY",0))
          +" never="+str(stats.get("NO_PERSONAL_OUTBOUND_EVIDENCE",0))
          +" QQ_latest="+latest.isoformat()
          +" (exact From+To/CC; no sends; never overwrites decisions)")
    api.values().update(spreadsheetId=DEST,range="'Automation Health'!A21:D21",
        valueInputOption="RAW",body={"values":[[
            "Lead My Sent Audit",now.strftime("%Y-%m-%d %H:%M:%S KST"),
            "PASS_VERIFIED",note]]}).execute()
    print("PERSONAL_LEAD_AUDIT_APPLIED_AND_VERIFIED=true",flush=True)


def build_service(data):
    creds=service_account.Credentials.from_service_account_info(
        data,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return google_build("sheets","v4",credentials=creds,cache_discovery=False).spreadsheets()


if __name__=="__main__":
    main()
