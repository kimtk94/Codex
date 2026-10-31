#!/usr/bin/env python3
"""Invoice-number-level coverage bridge: QQ canonical originals vs CSS legacy.

Writes only CSS Invoice Legacy Key Bridge generated audit tab. Never append to
Actuals, send mail, certify ownership/payment, or edit a legacy source.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"css_mail"))
from tax_invoice_extract import extract

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QQ="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
TAB="CSS Invoice Legacy Key Bridge"
KST=dt.timezone(dt.timedelta(hours=9))
MONTH="2026-10"
HEAD=["Invoice No","Issue Month KST","QQ Original Gross KRW (VAT incl)",
      "QQ Original Net KRW (VAT excl)","Legacy CSS Gross KRW",
      "Key Classification","Exact Amount Match","Source Evidence",
      "Revenue Treatment","Checked KST","GitHub Run"]
ALLOWED={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
NOTICE=re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY=re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
def cell(row,j):return str(row[j]).strip() if row is not None and len(row)>j and row[j] is not None else ""
def money(x):
    s=str(x).strip().replace(",","").replace(" KRW","").replace("₩","")
    if not re.fullmatch(r"\d+",s):raise ValueError("INVALID_CURRENCY_AMOUNT")
    return int(s)
def issue_month(raw):
    try:z=dt.datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except ValueError as e:raise ValueError("UNPARSABLE_ISSUE_DATE") from e
    if z.tzinfo is None:raise ValueError("ISSUE_DATE_WITHOUT_OFFSET")
    return z.astimezone(KST).strftime("%Y-%m")
def net(amount):
    return int((Decimal(amount)*Decimal(10)/Decimal(11)).quantize(Decimal(1),rounding=ROUND_HALF_UP))
def compare(source,legacy,net_month,now):
    if not source or cell(source[0],0)!="invoice_number" or cell(source[0],10)!="validation_status":
        raise ValueError("QQ_ORIGINAL_SCHEMA_INVALID")
    if not legacy or [cell(legacy[0],i) for i in (0,2,3)]!=["invoice_month","invoice_number","amount_krw"]:
        raise ValueError("LEGACY_CSS_SCHEMA_INVALID")
    if not net_month or [cell(net_month[0],i) for i in (0,1,2,4)] != [
        "Month","Issued Invoice Gross KRW (VAT incl)",
        "Issued Net Revenue KRW (VAT excl)","Issued Invoice Count"]:
        raise ValueError("NET_MONTHLY_SCHEMA_INVALID")
    official={}
    for x in source[1:]:
        id=cell(x,0)
        if cell(x,10) not in ALLOWED or not re.fullmatch(r"209126\d{6}",id):
            continue
        subject=cell(x,6)
        if REPLY.match(subject) or not NOTICE.match(subject):continue
        parsed=extract(cell(x,5))
        amount=money(cell(x,1))
        if not parsed or parsed[0]!=id or parsed[4]!=amount or amount<=0 or not cell(x,8):
            raise ValueError("ORIGINAL_FILENAME_OR_AMOUNT_INVALID")
        if issue_month(cell(x,7))!=MONTH:continue
        if id in official and official[id]!=amount:raise ValueError("ORIGINAL_KEY_CONFLICT")
        official[id]=amount
    existing={}
    for x in legacy[1:]:
        if cell(x,0)!=MONTH:continue
        id=cell(x,2)
        if not re.fullmatch(r"209126\d{6}",id):raise ValueError("LEGACY_KEY_INVALID")
        amount=money(cell(x,3))
        parsed=extract(cell(x,10))
        if not parsed or parsed[0]!=id or parsed[4]!=amount:
            raise ValueError("LEGACY_FILENAME_AMOUNT_CONFLICT")
        if id in existing:raise ValueError("LEGACY_DUPLICATE_KEY")
        existing[id]=amount
    if not official or not existing:raise ValueError("INVOICE_COVERAGE_EMPTY")
    if set(existing)-set(official):raise ValueError("LEGACY_KEY_NOT_IN_QQ_CANONICAL")
    if any(official[id]!=amount for id,amount in existing.items()):
        raise ValueError("OVERLAPPING_INVOICE_AMOUNT_CONFLICT")
    official_month=next((x for x in net_month[1:] if cell(x,0)==MONTH),None)
    if official_month is None:raise ValueError("OFFICIAL_MONTH_MISSING")
    gross=sum(official.values());total_net=sum(net(amount) for amount in official.values())
    if gross!=money(cell(official_month,1)) or total_net!=money(cell(official_month,2)) or len(official)!=money(cell(official_month,4)):
        raise ValueError("OFFICIAL_MONTH_TOTAL_CONFLICT")
    stamp=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    rows=[]
    for id,amount in sorted(official.items()):
        old=existing.get(id)
        rows.append([id,MONTH,amount,net(amount),old if old is not None else "",
           "MATCHED_LEGACY" if old is not None else "NEW_QQ_ONLY",
           "EXACT" if old is not None else "NOT_IN_LEGACY",
           "QQ original CSS notice + attachment filename",
           "CANONICAL_ALREADY_COUNTED;DO_NOT_ADD_AGAIN",stamp,""])
    added=[v for k,v in official.items() if k not in existing]
    return rows,{"month":MONTH,"canonical_count":len(official),"legacy_count":len(existing),
        "new_qq_only_count":len(added),"new_qq_only_gross":sum(added),
        "canonical_gross":gross,"canonical_net":total_net,"overlap_conflicts":0,
        "source_writes":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("CKD_DRIVE_SA_JSON","")
    run=os.getenv("GITHUB_RUN_ID","")
    if not raw or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("MISSING_APPROVED_GITHUB_SOURCE")
    session=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    def req(method,url,**kwargs):
        r=session.request(method,url,timeout=55,**kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}
    def read(book,title,range_):
        uri=("https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+
            urllib.parse.quote("'"+title+"'!"+range_,safe=""))
        return req("GET",uri).get("values",[])
    source=read(QQ,"CSS Tax Invoice Extract","A1:L10000")
    legacy=read(BOOK,"CSS Tax Invoices","A1:N10000")
    official=read(BOOK,"BI Revenue Net VAT Monthly","A1:I24")
    rows,metrics=compare(source,legacy,official,dt.datetime.now(KST))
    out=[HEAD]+[row[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for row in rows]
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    meta=req("GET",root,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(p["properties"]["title"]==TAB for p in meta.get("sheets",[])):
        req("POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":250,"columnCount":len(HEAD),"frozenRowCount":1}}}}]})
    address=root+"/values/"+urllib.parse.quote("'"+TAB+"'!A1:K"+str(len(out)),safe="")
    old=req("GET",address).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("FOREIGN_BRIDGE_SHEET_REFUSE_OVERWRITE")
    req("PUT",address,params={"valueInputOption":"RAW"},json={"values":out})
    back=req("GET",address).get("values",[])
    if back!=[[str(c) for c in row] for row in out]:
        raise RuntimeError("INVOICE_KEY_BRIDGE_READBACK_MISMATCH")
    print("CSS_EXACT_KEY_BRIDGE="+json.dumps(metrics,sort_keys=True))
    print("CANONICAL_REVENUE_ALREADY_COUNTS_NEW_KEYS;NO_DOUBLE_BOOKING;NO_SOURCE_EDIT")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_INVOICE_KEY_BRIDGE_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
