#!/usr/bin/env python3
"""Refresh Lead sent audit using outgoing QQ messages with exact recipient match.

Preserve previously confirmed audits; never classify missing evidence as no reply.
Default dry-run. Only evidence after Lead creation is eligible.
"""
import os,json,base64,re,sys,datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
QQ=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
ALLOWED_SENDERS={"taehoon.kim@novogene.com","masiyuan8900@novogene.com","jiin.yoo@novogene.com"}
MAIL_RE=re.compile(r"(?<![\w.+-])([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})(?![\w.-])")
def val(row,i):return str(row[i]).strip() if i<len(row) and row[i] is not None else ""
def date(text):
    try:
        parsed=datetime.datetime.fromisoformat(text.replace("Z","+00:00"))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        return parsed
    except ValueError:return None
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("Missing Google credential")
    try:key=json.loads(raw)
    except ValueError:key=json.loads(base64.b64decode(raw))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        key,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
    def read(book,tab,area):
        return api.get(spreadsheetId=book,range="'"+tab+"'!"+area,valueRenderOption="FORMATTED_VALUE").execute().get("values",[])
    leads=read(SFDC,"Lead Email Followup","A1:G600")
    audits=read(QQ,"SFDC Lead Sent Audit","A1:E600")
    # Read narrow columns only: date (C), sender (E), recipient (F), direction (U).
    # A:U includes large mail bodies in Q; do not download those bodies.
    # One API request for four narrow columns; avoids repeated Sheets quota charges.
    mail_ranges=["'All Emails'!C1:C60000","'All Emails'!E1:E60000",
                 "'All Emails'!F1:F60000","'All Emails'!U1:U60000"]
    mail_blocks=api.batchGet(spreadsheetId=QQ,ranges=mail_ranges,
                              valueRenderOption="FORMATTED_VALUE").execute().get("valueRanges",[])
    if len(mail_blocks)!=len(mail_ranges):
        raise RuntimeError("Incomplete QQ mail batch read; no writes")
    dates,senders,recipients,directions=[block.get("values",[]) for block in mail_blocks]
    sf_evidence=read(SFDC,"Lead Email Followup","X2:Z600")
    if not leads or not audits or not directions or not dates or not senders or not recipients:
        raise RuntimeError("Missing audit source")
    if val(leads[0],0)!="Lead ID" or val(audits[0],0)!="Lead ID" or val(directions[0],0)!="direction":
        raise RuntimeError("Unexpected source header; no writes")
    if [val(dates[0],0),val(senders[0],0),val(recipients[0],0)]!=["received_at","from_email","to"]:
        raise RuntimeError("Unexpected email evidence columns; no writes")
    if max(map(len,(dates,senders,recipients,directions)))>=60000:
        raise RuntimeError("Mail scan capacity reached; refuse partial audit")
    # Audit index by Lead ID and existing row number.
    audit_ids=[val(r,0) for r in audits[1:] if val(r,0)]
    if len(audit_ids)!=len(set(audit_ids)):
        raise RuntimeError("Duplicate audit Lead ID; no writes")
    existing={val(r,0):(i,r) for i,r in enumerate(audits[1:],start=2) if val(r,0)}
    lead_ids=[val(r,0) for r in leads[1:] if val(r,0)]
    if len(lead_ids)!=len(set(lead_ids)):
        raise RuntimeError('Duplicate source Lead ID; no writes')
    sent={}
    for idx in range(1,max(map(len,(dates,senders,recipients,directions)))):
        direction=val(directions[idx],0).lower() if idx<len(directions) else ""
        if direction not in ("sent","outbound"):continue
        sender=val(senders[idx],0).lower() if idx<len(senders) else ""
        if sender not in ALLOWED_SENDERS:continue
        at=date(val(dates[idx],0)) if idx<len(dates) else None
        if not at:continue
        for addr in set(x.lower() for x in MAIL_RE.findall(val(recipients[idx],0) if idx<len(recipients) else "")):
            sent.setdefault(addr,[]).append(at)
    # A successful dry-run with no updates is not proof of fresh mail coverage.
    source_dates=[date(val(row,0)) for row in dates[1:] if row]
    source_latest=max((x for x in source_dates if x),default=None)
    source_age_days=(datetime.datetime.now(datetime.timezone.utc)-source_latest.astimezone(datetime.timezone.utc)).total_seconds()/86400 if source_latest else None
    source_stale=source_age_days is None or source_age_days>2
    if source_stale:
        print("LEAD_SENT_AUDIT_SOURCE_STALE=true; historical sent matches only",flush=True)
    # Current metadata-only IMAP staging supplements the historical All Emails source.
    # Exact recipient plus authorized sender and OUTBOUND direction are required.
    staging_ranges=["'CSS Git Ingest'!F1:H100000","'CSS Git Ingest'!P1:P100000"]
    stage=api.batchGet(spreadsheetId=QQ,ranges=staging_ranges,
                       valueRenderOption="FORMATTED_VALUE").execute().get("valueRanges",[])
    if len(stage)!=2:
        raise RuntimeError("Incomplete CSS Git Ingest read")
    details=stage[0].get("values",[])
    flags=stage[1].get("values",[])
    if not details or details[0][:3]!=["received_at","from_email","recipient_to"] or not flags or val(flags[0],0)!="direction":
        raise RuntimeError("Unexpected CSS Git Ingest headers")
    if len(details)>=100000 or len(flags)>=100000:
        raise RuntimeError("CSS Git Ingest scan limit reached")
    stage_sent=0
    historical_cutoff=source_latest
    for idx in range(1,max(len(details),len(flags))):
        if idx>=len(flags) or val(flags[idx],0).upper()!="OUTBOUND":
            continue
        row=details[idx] if idx<len(details) else []
        sender=val(row,1).lower()
        at=date(val(row,0))
        if sender not in ALLOWED_SENDERS or not at or (historical_cutoff and at<=historical_cutoff):
            continue
        for recipient in set(x.lower() for x in MAIL_RE.findall(val(row,2))):
            sent.setdefault(recipient,[]).append(at)
            stage_sent+=1
    stage_dates=[date(val(row,0)) for row in details[1:] if row]
    stage_latest=max((x for x in stage_dates if x),default=None)
    if stage_latest and (not source_latest or stage_latest>source_latest):
        source_latest=stage_latest
    source_age_days=(datetime.datetime.now(datetime.timezone.utc)-source_latest.astimezone(datetime.timezone.utc)).total_seconds()/86400 if source_latest else None
    source_stale=source_age_days is None or source_age_days>2
    print("LEAD_SENT_AUDIT_CSS_STAGE_OUTBOUND_MATCHES="+str(stage_sent),flush=True)
    updates=[];sf_updates=[];changed=0
    for lead_row,r in enumerate(leads[1:],start=2):
        lead_id=val(r,0);email=val(r,3).lower()
        if not lead_id or not email or lead_id not in existing:continue
        i,old=existing[lead_id]
        created=date(val(r,5))
        if not created:continue
        if created.tzinfo is None:created=created.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        qualifying=[d for d in sent.get(email,[]) if d>=created]
        if not qualifying:continue
        latest=max(qualifying).isoformat()
        prior=date(val(old,2))
        if prior and prior.tzinfo is None:prior=prior.replace(tzinfo=created.tzinfo)
        effective_at=max(prior,max(qualifying)) if prior else max(qualifying)
        effective_latest=effective_at.isoformat()
        count=max(len(qualifying),int(val(old,3) or 0))
        if val(old,4)!='SENT_CONFIRMED' or not prior or prior<max(qualifying):
            updates.append({'range':"'SFDC Lead Sent Audit'!C"+str(i)+':E'+str(i),
                            'values':[[effective_latest,str(count),'SENT_CONFIRMED']]})
            changed+=1
        sf_current=sf_evidence[lead_row-2] if lead_row-2<len(sf_evidence) else []
        sf_prior=date(val(sf_current,0))
        if sf_prior and sf_prior>effective_at:continue
        if sf_prior!=effective_at or val(sf_current,2)!='SENT_CONFIRMED' or val(sf_current,1)!=str(count):
            sf_updates.append({'range':"'Lead Email Followup'!X"+str(lead_row)+':Z'+str(lead_row),
                               'values':[[effective_latest,str(count),'SENT_CONFIRMED']]})
    dry=os.getenv("DRY_RUN","true").lower()!="false"
    print(json.dumps({"dry_run":dry,"source_mails":max(map(len,(dates,senders,recipients,directions)))-1,"sent_addresses":len(sent),"audit_updates":changed,"sfdc_updates":len(sf_updates),"source_latest":source_latest.isoformat() if source_latest else None,"source_stale":source_stale}))
    if not dry and source_stale:
        raise RuntimeError('Lead audit source is stale; refusing writes')
    if not dry:
        if updates:
            api.batchUpdate(spreadsheetId=QQ,body={"valueInputOption":"RAW","data":updates}).execute()
        if sf_updates:
            api.batchUpdate(spreadsheetId=SFDC,body={"valueInputOption":"RAW","data":sf_updates}).execute()
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print(type(ex).__name__+": "+str(ex),file=sys.stderr);sys.exit(1)
