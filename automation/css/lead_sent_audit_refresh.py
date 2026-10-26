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
    dates=read(QQ,"All Emails","C1:C60000")
    senders=read(QQ,"All Emails","E1:E60000")
    recipients=read(QQ,"All Emails","F1:F60000")
    directions=read(QQ,"All Emails","U1:U60000")
    sf_evidence=read(SFDC,"Lead Email Followup","X2:Z600")
    if not leads or not audits or not directions:
        raise RuntimeError("Missing audit source")
    if val(leads[0],0)!="Lead ID" or val(audits[0],0)!="Lead ID" or val(directions[0],0)!="direction":
        raise RuntimeError("Unexpected source header; no writes")
    if [val(dates[0],0),val(senders[0],0),val(recipients[0],0)]!=["received_at","from_email","to"]:
        raise RuntimeError("Unexpected email evidence columns; no writes")
    if max(map(len,(dates,senders,recipients,directions)))>=60000:
        raise RuntimeError("Mail scan capacity reached; refuse partial audit")
    # Audit index by Lead ID and existing row number.
    existing={val(r,0):(i,r) for i,r in enumerate(audits[1:],start=2) if val(r,0)}
    sent={}
    if len(set(existing))!=len(existing):
        raise RuntimeError("Duplicate audit Lead ID")
    for idx in range(1,max(map(len,(dates,senders,recipients,directions)))):
        direction=val(directions[idx],0).lower() if idx<len(directions) else ""
        if direction not in ("sent","outbound"):continue
        sender=val(senders[idx],0).lower() if idx<len(senders) else ""
        if sender not in ALLOWED_SENDERS:continue
        at=date(val(dates[idx],0)) if idx<len(dates) else None
        if not at:continue
        for addr in set(x.lower() for x in MAIL_RE.findall(val(recipients[idx],0) if idx<len(recipients) else "")):
            sent.setdefault(addr,[]).append(at)
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
        if val(old,4)=="SENT_CONFIRMED" and prior and prior>=max(qualifying):continue
        # Exact outgoing address and post-creation timestamp only, not thread-level reply proof.
        updates.append({"range":"'SFDC Lead Sent Audit'!C"+str(i)+":E"+str(i),
                        "values":[[latest,str(max(len(qualifying),int(val(old,3) or 0))),"SENT_CONFIRMED"]]})
        changed+=1
        sf_current=sf_evidence[lead_row-2] if lead_row-2<len(sf_evidence) else []
        if val(sf_current,0)!=latest or val(sf_current,2)!="SENT_CONFIRMED":
            sf_updates.append({"range":"\'Lead Email Followup\'!X"+str(lead_row)+":Z"+str(lead_row),
                               "values":[[latest,str(max(len(qualifying),int(val(old,3) or 0))),"SENT_CONFIRMED"]]})
    dry=os.getenv("DRY_RUN","true").lower()!="false"
    print(json.dumps({"dry_run":dry,"source_mails":max(map(len,(dates,senders,recipients,directions)))-1,"sent_addresses":len(sent),"audit_updates":changed,"sfdc_updates":len(sf_updates)}))
    if not dry and updates:
        api.batchUpdate(spreadsheetId=QQ,body={"valueInputOption":"RAW","data":updates}).execute()
        if sf_updates:
            api.batchUpdate(spreadsheetId=SFDC,body={"valueInputOption":"RAW","data":sf_updates}).execute()
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print(type(ex).__name__+": "+str(ex),file=sys.stderr);sys.exit(1)
