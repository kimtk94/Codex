#!/usr/bin/env python3
"""Read Salesforce subscribed Quotation Report attachments from authorized QQ IMAP.
No outbound emails, no mailbox mutations, no Salesforce writes.
"""
import csv, datetime as dt, email, imaplib, io, json, os, re, sys, time, urllib.parse
from email import policy
from html.parser import HTMLParser
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SHEET=os.getenv("SFDC_UNIFIED_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
KST=dt.timezone(dt.timedelta(hours=9))
HEADER=["Salesforce Record ID","IsActive","Grand Total","CurrencyIsoCode","Opportunity ID","Last Modified Date","Quotation Name","AMEA Quotation ID","Source URL","Exported At KST"]
FIELDS=["Quotation: SFDC Quotation ID","Opportunity ID","Quotation: ID","Quotation Name","Active","Exclude Tax After Discount USD"]
class TableParser(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.row=[]
        elif tag in ("td","th") and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()));self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None
def parse_attachment(blob,filename):
    raw=blob.decode("utf-8-sig","replace")
    if "<table" in raw[:10000].lower() or "<tr" in raw[:10000].lower():
        parser=TableParser();parser.feed(raw);table=parser.rows
    else:
        table=list(csv.reader(io.StringIO(raw)))
    if not table:return []
    heads=table[0]
    if not set(FIELDS).issubset(set(heads)):return []
    idx={h:heads.index(h) for h in FIELDS}
    rows=[]
    for record in table[1:]:
        if len(record)<len(heads):continue
        sid=record[idx["Quotation: ID"]].strip()
        flag=record[idx["Active"]].strip()
        qid=record[idx["Quotation: SFDC Quotation ID"]].strip()
        amount=record[idx["Exclude Tax After Discount USD"]].replace(",","").strip()
        if not re.fullmatch(r"a0P[A-Za-z0-9]{12,15}",sid):continue
        if flag not in ("0","1") or not re.fullmatch(r"\d+(?:\\.\d+)?",amount):continue
        rows.append([sid,flag,float(amount),"USD",record[idx["Opportunity ID"]],"",record[idx["Quotation Name"]],qid,"",""])
    return rows
def sheet_call(session,method,suffix,**kwargs):
    base="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET
    for attempt in range(6):
        resp=session.request(method,base+suffix,timeout=60,**kwargs)
        if resp.status_code in (429,500,502,503,504) and attempt<5:
            time.sleep(min(60,2**attempt));continue
        if not resp.ok:raise RuntimeError("SHEETS_HTTP_"+str(resp.status_code))
        return resp.json() if resp.content else {}
def main():
    user=os.environ["CSS_QQ_MAIL_ADDRESS"];auth=os.environ["CSS_QQ_MAIL_AUTH_CODE"]
    since=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=3)).strftime("%d-%b-%Y")
    selected=None
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(user,auth);im.select("INBOX",readonly=True)
        ok,hits=im.uid("SEARCH",None,"SINCE",since)
        if ok!="OK":raise RuntimeError("IMAP_SEARCH_FAILED")
        for uid in (hits[0] or b"").split()[-500:]:
            ok,parts=im.uid("FETCH",uid,"(BODY.PEEK[])")
            if ok!="OK":continue
            payload=next((p[1] for p in parts if isinstance(p,tuple)),None)
            if not payload:continue
            msg=email.message_from_bytes(payload,policy=policy.default)
            subject=str(msg.get("subject",""))
            if "quotation report" not in subject.lower() and "quotation" not in subject.lower():continue
            for part in msg.walk():
                filename=str(part.get_filename() or "")
                if not filename.lower().endswith((".xls",".xlsx",".csv")):continue
                data=part.get_payload(decode=True)
                if not data or len(data)>8_000_000:continue
                if filename.lower().endswith(".xlsx"):continue  # Requires a separate XLSX parser, fail closed.
                rows=parse_attachment(data,filename)
                if len(rows)<100 or len(rows)!=len({r[0] for r in rows}):continue
                try:date=email.utils.parsedate_to_datetime(str(msg["date"]))
                except (ValueError,TypeError):continue
                if not date:continue
                stamp=date.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
                if selected is None or date>selected[0]:selected=(date,stamp,rows)
    if selected is None:
        print("SFDC_QUOTE_EMAIL: NO_VALID_ATTACHMENT (no source overwritten)")
        return 0
    stamp=selected[1];rows=selected[2]
    for row in rows:row[-1]=stamp
    credentials=service_account.Credentials.from_service_account_info(json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session=AuthorizedSession(credentials)
    meta=sheet_call(session,"GET","?fields=sheets.properties.title")
    if "SFDC Quote Export" not in {x["properties"]["title"] for x in meta["sheets"]}:raise RuntimeError("TARGET_SHEET_MISSING")
    # One single update of the generated Quote Export, with no changes to other tabs.
    cell=urllib.parse.quote("'SFDC Quote Export'!A1",safe="")
    sheet_call(session,"PUT","/values/"+cell+"?valueInputOption=RAW",json={"values":[HEADER]+rows})
    health=urllib.parse.quote("'Automation Health'!A7",safe="")
    sheet_call(session,"PUT","/values/"+health+"?valueInputOption=RAW",json={"values":[["SFDC Quote Report Email",stamp,"PASS","rows="+str(len(rows))+" active="+str(sum(r[1]=="1" for r in rows))]]})
    print("SFDC_QUOTE_EMAIL_PASS rows="+str(len(rows))+" active="+str(sum(r[1]=="1" for r in rows)))
    return 0
if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("SFDC_QUOTE_EMAIL_FAILED "+type(exc).__name__,file=sys.stderr);raise
