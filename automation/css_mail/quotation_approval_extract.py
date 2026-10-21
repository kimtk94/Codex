#!/usr/bin/env python3
"""Readonly quotation approval evidence feed. No prices or Salesforce mutations."""
import datetime as dt
import email
import imaplib
import os
import re
import sys
import urllib.parse
from email import policy
from html import unescape
from html.parser import HTMLParser
import incremental_sync as mail

TAB="Quotation Approval Auto"
COLS=["approval_mail_at_kst","quotation_id","quotation_name","salesforce_record_id",
      "quotation_created_date","approval_evidence","subject","uid","ingest_key",
      "message_id","review_status","checked_at_utc"]
ALERT=re.compile(r"for\s+approval\s+quotation\s+alert",re.I)
PROJECT=re.compile(r"AMEA\d{7,}(?:-\d+)?",re.I)
QID=re.compile(r"QID[- ]\d{4}[- ]\d{2}[- ]\d{2}[- ]\d+",re.I)
SFID=re.compile(r"\b(?:a0P[A-Za-z0-9]{12,15})\b")
CREATED=re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
APPROVED=re.compile(r"\bapproved\b|approval\s+completed|승인\s*완료",re.I)
class HtmlText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            self.parts.extend(value for k,value in attrs if k=="href" and value)
    def text(self):return unescape(" ".join(self.parts))
def body_text(message):
    values=[]
    for part in message.walk():
        if part.get_content_type() not in ("text/plain","text/html"):continue
        try: content=part.get_content()
        except (ValueError,UnicodeError,LookupError):continue
        if part.get_content_type()=="text/html":
            parser=HtmlText();parser.feed(str(content));content=parser.text()
        values.append(str(content))
    return "\\n".join(values)[:120000]

def read(s,tab,a1):
    u=urllib.parse.quote("'"+tab+"'!"+a1,safe="")
    vals=mail.api(s,"GET",mail.endpoint("/values/"+u)).get("values",[])
    if not vals:return []
    return [dict(zip(vals[0],r+[""]*(len(vals[0])-len(r)))) for r in vals[1:] if any(r)]

def main():
    s=mail.authorize()
    original=read(s,"CSS Git Ingest","A1:P100000")
    original=[m for m in original if m.get("direction")=="INBOUND" and ALERT.search(m.get("subject",""))]
    existing=read(s,"Quotation Approval List","A1:U10000")
    meta=mail.api(s,"GET",mail.endpoint()+"?fields=sheets.properties.title")
    tabs={x["properties"]["title"] for x in meta.get("sheets",[])}
    previous=read(s,TAB,"A1:L10000") if TAB in tabs else []
    known={str(x.get("uid","")).strip().lower() for x in existing}
    output={r["ingest_key"]:r for r in previous if r.get("ingest_key")}
    legacy_by_uid={str(r.get("uid","")).strip().lower():r for r in existing}
    reconciled=0
    for row in original:
        key=row.get("ingest_key","")
        if not key:continue
        uid="inbox:"+str(row.get("imap_uid",""))
        old=legacy_by_uid.get(uid.lower())
        if not old:continue
        output[key]={
            "approval_mail_at_kst":old.get("approved_at_kst",""),
            "quotation_id":old.get("quotation_id",""),
            "quotation_name":old.get("quotation_name",""),
            "salesforce_record_id":old.get("salesforce_record_id",""),
            "quotation_created_date":old.get("quotation_created_date",""),
            "approval_evidence":"VERIFIED_LEGACY_RECORD",
            "subject":row.get("subject",""),"uid":uid,"ingest_key":key,
            "message_id":row.get("message_id",""),"review_status":"APPROVED_IN_LEGACY",
            "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
        reconciled+=1
    pending=[r for r in original if r.get("ingest_key") not in output or output[r["ingest_key"]].get("review_status")=="REVIEW_REQUIRED"]
    pending.sort(key=lambda m:m.get("received_at",""),reverse=True)
    batch=pending[:int(os.getenv("CSS_APPROVAL_BATCH","70"))]
    if batch:
        with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
            im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
            state,_=im.select("INBOX",readonly=True)
            if state!="OK":raise RuntimeError("Approval INBOX unavailable")
            state,uv=im.response("UIDVALIDITY")
            valid=(uv[0] or b"").decode() if uv else ""
            for r in batch:
                if r.get("uidvalidity")!=valid:continue
                state,pieces=im.uid("FETCH",r["imap_uid"],"(BODY.PEEK[])")
                if state!="OK":raise RuntimeError("Approval mail fetch failed")
                content=b"".join(x[1] for x in pieces or [] if isinstance(x,tuple) and isinstance(x[1],bytes))
                if not content:continue
                # Parse plain text evidence only; do not retain private body contents.
                message=email.message_from_bytes(content,policy=policy.default)
                value=body_text(message)
                combined=r.get("subject","")+"\n"+value
                projects=PROJECT.findall(combined)
                qids=QID.findall(combined)
                sids=SFID.findall(combined)
                dates=CREATED.findall(combined)
                evidence="APPROVED_TEXT" if APPROVED.search(value) else "ALERT_ONLY"
                uid="inbox:"+r["imap_uid"]
                # Existing listing is proof of historical classification.
                if uid.lower() in known:evidence="EXISTS_IN_LEGACY"
                when=mail.date_str(r.get("received_at",""))
                try:when=dt.datetime.fromisoformat(when).astimezone(mail.KST).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError,TypeError):when=r.get("received_at","")
                output[r["ingest_key"]]={
                    "approval_mail_at_kst":when,
                    "quotation_id":projects[0] if projects else "",
                    "quotation_name":qids[0] if qids else "",
                    "salesforce_record_id":sids[0] if sids else "",
                    "quotation_created_date":dates[0] if dates else "",
                    "approval_evidence":evidence,
                    "subject":r.get("subject",""),"uid":uid,"ingest_key":r["ingest_key"],
                    "message_id":r.get("message_id",""),
                    "review_status":"APPROVED" if evidence in ("APPROVED_TEXT","EXISTS_IN_LEGACY") else "REVIEW_REQUIRED",
                    "checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat()}
            im.logout()
    if TAB not in tabs:
        mail.api(s,"POST",mail.endpoint(":batchUpdate"),json={"requests":[{"addSheet":{"properties":{"title":TAB,"gridProperties":{"frozenRowCount":1}}}}]})
    data=[COLS]+[[x.get(k,"") for k in COLS] for x in sorted(output.values(),key=lambda r:r.get("approval_mail_at_kst",""),reverse=True)]
    if len(data)>10000:raise RuntimeError("Approval feed capacity exceeded")
    def addr(cell):return urllib.parse.quote("'"+TAB+"'!"+cell,safe="")
    # Dedicated generated tab only. Legacy data and SFDC fields untouched.
    mail.api(s,"POST",mail.endpoint("/values/"+addr("A1:L10000")+":clear"),json={})
    mail.api(s,"PUT",mail.endpoint("/values/"+addr("A1"))+"?valueInputOption=RAW",json={"values":data})
    print("CSS_QUOTE_APPROVAL_PASS legacy="+str(len(existing))+" selected="+str(len(batch))+" total="+str(len(output))+" reconciled_legacy="+str(reconciled)+" price_enrichment=SFDC_LATER")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CSS_QUOTE_APPROVAL_FAILED "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
