#!/usr/bin/env python3
"""Read-only QQ subscribed SFDC Quote Report attachment schema audit.

No customer rows, mailbox subjects, sender addresses, message IDs, filenames,
amounts, secrets or attachments are printed/persisted.
Only aggregate counts/verified field-schema and date bounds.
"""
import csv
import datetime as dt
from email import policy
from email.utils import parsedate_to_datetime
import email
from html.parser import HTMLParser
import imaplib
import io
import json
import os
import re
import sys
from collections import Counter
from openpyxl import load_workbook

REQUIRED={
  "SFDC Quotation ID","Quotation Product ID","Process Name: SFDC Process ID",
  "Quote Process Name","Unit Price USD","Sample Quantity","Data Size",
  "Total Price USD (converted)","Sales Price USD (converted)","Created Date",
}
PROCESS_HEAD=set([
  "SFDC Quotation ID","Quotation Product ID","Contact Name: Full Name",
  "Contact ID","Email","Opportunity Name: Opportunity Name","Opportunity ID",
  "Account Name: Account Name","*Account Id","Active","Sync CMS",
  "Opportunity Amount USD","Total Price USD (converted) Currency",
  "Total Price USD (converted)","Sales Price USD (converted) Currency",
  "Sales Price USD (converted)","Unit Price USD",
  "Quotation Process Name","Process Name: SFDC Process ID",
  "Quote Process Name","Created Date","Quotation PDF Created Time",
  "Data Unit","Sample Quantity","Data Size"
])
QUOTE_HEAD={"Quotation: SFDC Quotation ID","Quotation: ID",
 "Exclude Tax After Discount USD","Opportunity ID"}
MAX_ATTACH_BYTES=10000000

class FirstTable(HTMLParser):
  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.row=[];self.cell=None;self.head=None;self.rows=0
  def handle_starttag(self,tag,attrs):
    if tag=="tr":self.row=[]
    elif tag in ("td","th"):self.cell=[]
  def handle_data(self,data):
    if self.cell is not None:self.cell.append(data)
  def handle_endtag(self,tag):
    if tag in ("td","th") and self.cell is not None:
      self.row.append(" ".join("".join(self.cell).split()))
      self.cell=None
    elif tag=="tr" and self.row:
      if self.head is None:self.head=self.row
      else:self.rows+=1

def decode(blob):
  probe=blob[:1000].lower()
  if b"euc-kr" in probe or b"ks_c_5601" in probe:return blob.decode("euc-kr")
  if b"charset=cp949" in probe:return blob.decode("cp949")
  try:return blob.decode("utf-8-sig")
  except UnicodeDecodeError:return blob.decode("cp949")

def inspect_attachment(blob,filename):
  if len(blob)>MAX_ATTACH_BYTES:return {"kind":"too_large","rows":0}
  if filename.lower().endswith(".xlsx"):
    wb=load_workbook(io.BytesIO(blob),read_only=True,data_only=True)
    try:
      values=wb.active.iter_rows(values_only=True)
      heads=next(values,[])
      heads=["" if x is None else str(x).strip() for x in heads]
      count=sum(1 for row in values if any(x is not None for x in row))
    finally:wb.close()
  else:
    decoded=decode(blob)
    if "<table" in decoded[:10000].lower() or "<tr" in decoded[:10000].lower():
      p=FirstTable();p.feed(decoded)
      heads=p.head or [];count=p.rows
    else:
      reader=csv.reader(io.StringIO(decoded))
      heads=[x.strip() for x in next(reader,[])];count=sum(1 for row in reader if any(x.strip() for x in row))
  head=set(heads)
  if head==PROCESS_HEAD and len(heads)==25:kind="detail_exact_25"
  elif REQUIRED.issubset(head):kind="detail_partial_schema"
  elif QUOTE_HEAD.issubset(head):kind="quotation_header"
  else:kind="other_schema"
  return {"kind":kind,"rows":count,"columns":len(heads),
    "required_detail_fields_found":len(head.intersection(REQUIRED)),
    "all_25_present":PROCESS_HEAD.issubset(head)}

def audit(days=14):
  diagnostics=Counter()
  report_rows=[]
  user=os.environ["CSS_QQ_MAIL_ADDRESS"]
  secret=os.environ["CSS_QQ_MAIL_AUTH_CODE"]
  since=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=days)).strftime("%d-%b-%Y")
  with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
    im.login(user,secret)
    im.select("INBOX",readonly=True)
    ok,recent=im.uid("SEARCH",None,"SINCE",since)
    if ok!="OK":raise RuntimeError("IMAP_QUERY_UNAVAILABLE")
    ok2,special=im.uid("SEARCH",None,"SINCE",since,"SUBJECT",'"Report results"')
    all_uids=(recent[0] or b"").split()
    direct=(special[0] or b"").split() if ok2=="OK" else []
    chosen=sorted(set(all_uids[-700:]+direct),key=lambda b:int(b))
    diagnostics["mail_uids_checked"]=len(chosen)
    diagnostics["exact_report_results_subject_hits"]=len(direct)
    for uid in chosen:
      ok,msg=im.uid("FETCH",uid,"(BODY.PEEK[])")
      if ok!="OK":diagnostics["fetch_failures"]+=1;continue
      payload=next((t[1] for t in msg if isinstance(t,tuple)),None)
      if not payload:continue
      message=email.message_from_bytes(payload,policy=policy.default)
      subject=str(message.get("subject","")).lower()
      if not any(w in subject for w in ("report","quotation","quote","salesforce")):
        continue
      diagnostics["report_subjects"]+=1
      sender=str(message.get("from","")).lower()
      sf_sender=bool(re.search(r"@(?:[a-z0-9-]+\.)*salesforce\.com\b",sender))
      for part in message.walk():
        filename=part.get_filename()
        if not filename or not filename.lower().endswith((".csv",".xls",".xlsx")):
          continue
        diagnostics["report_attachments"]+=1
        data=part.get_payload(decode=True)
        if not data:
          diagnostics["empty_attachments"]+=1
          continue
        try:
          info=inspect_attachment(data,filename)
          diagnostics["schema_"+info["kind"]]+=1
          if info["kind"].startswith("detail"):
            diagnostics["detail_from_salesforce"]+=int(sf_sender)
            when=parsedate_to_datetime(str(message.get("date","")))
            if when and when.tzinfo:
              report_rows.append({
                "kind":info["kind"],
                "rows":info["rows"],
                "columns":info["columns"],
                "from_salesforce":sf_sender,
                "received_date_utc":when.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
              })
        except (UnicodeError,ValueError,TypeError,IndexError,KeyError,OSError):
          diagnostics["attachment_parse_errors"]+=1
  # No individual email/attachment identifiers, content, subjects or prices.
  return {"status":"PASS","mode":"AUDIT_ONLY",
    "days":days,"counts":dict(sorted(diagnostics.items())),
    "detail_reports_by_received_date":sorted(report_rows,
      key=lambda x:x["received_date_utc"],reverse=True)[:10],
    "saved_rows":0,"crm_writes":0,"feishu_writes":0,"mail_writes":0}

def main():
  try:print(json.dumps(audit(),ensure_ascii=False,sort_keys=True))
  except Exception as exc:
    print(json.dumps({"status":"SOURCE_UNAVAILABLE","reason":type(exc).__name__,
      "saved_rows":0,"crm_writes":0,"feishu_writes":0,"mail_writes":0}),file=sys.stderr)
    return 2
  return 0
if __name__=="__main__":sys.exit(main())
