#!/usr/bin/env python3
"""Classify dated-only Feishu eTax rows against original personal QQ invoices.

Read-only source verification. Writes ONLY an isolated generated review tab;
never changes Revenue Actual, Feishu originals, source mirrors or user decisions.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"css_mail"))
from tax_invoice_extract import extract

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QQ_BOOK="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
TAB="Feishu eTax Personal QQ Coverage"
KST=ZoneInfo("Asia/Seoul")
HEAD=["Source Key Type","Feishu Invoice Key","CMS Invoice No",
      "Feishu Gross KRW","Personal QQ Gross KRW",
      "Personal QQ Evidence","Source Sales Label (not owner)",
      "Dated Snapshot","Source Age Days","Finance Decision",
      "Evidence Boundary","Checked KST","GitHub Run"]
ALLOWED={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
REPLY=re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
NOTICE=re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)

def cell(r,i):
    return str(r[i]).strip() if r is not None and i<len(r) and r[i] is not None else ""

def amount(value):
    t=str(value or "").strip().replace(",","").replace("₩","").replace(" KRW","")
    if not re.fullmatch(r"\d+(?:\.0{1,2})?",t):
        return None
    return int(t.split(".")[0])

def original_qq(rows):
    if not rows or cell(rows[0],0)!="invoice_number" or cell(rows[0],10)!="validation_status":
        raise ValueError("QQ_EXTRACT_SCHEMA_INVALID")
    invoices={}
    for row in rows[1:]:
        key=cell(row,0)
        if cell(row,10) not in ALLOWED or not re.fullmatch(r"\d{10,15}",key):continue
        subject=cell(row,6)
        if REPLY.match(subject) or not NOTICE.match(subject):continue
        parsed=extract(cell(row,5))
        value=amount(cell(row,1))
        if not parsed or parsed[0]!=key or parsed[4]!=value or value is None or value<=0 or not cell(row,8):
            raise ValueError("QQ_ORIGINAL_EVIDENCE_INTEGRITY_"+key)
        if key in invoices and invoices[key]!=value:
            raise ValueError("QQ_ORIGINAL_DUPLICATE_AMOUNT_CONFLICT")
        invoices[key]=value
    if not invoices:raise ValueError("QQ_ORIGINAL_EMPTY")
    return invoices

def audit(crosswalk,dated,qq,manifest,now):
    if now.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not crosswalk or [cell(crosswalk[0],i) for i in (0,1,2,3,4,5,7)] != [
            "Key Type","Invoice Identifier","Base Amount KRW",
            "Dated Sheet Amount KRW","Evidence","Snapshot Date","Payment / Issuance"]:
        raise ValueError("CROSSWALK_SCHEMA_INVALID")
    if not dated or [cell(dated[0],i) for i in (4,5,15,25)] != [
            "ERP Invoice Number","CMS Invoice Num","Amount","Sales"]:
        raise ValueError("DATED_ETAX_MIRROR_SCHEMA_INVALID")
    if not manifest or cell(manifest[0],0)!="Source" or cell(manifest[0],1)!="Source Date":
        raise ValueError("FEISHU_MANIFEST_SCHEMA_INVALID")
    source=[r for r in manifest[1:] if cell(r,0)=="eTax Invoice"]
    if len(source)!=1:raise ValueError("ETAX_MANIFEST_NOT_UNIQUE")
    try:
        effective=dt.date.fromisoformat(cell(source[0],1))
    except ValueError as err:raise ValueError("ETAX_MANIFEST_DATE_INVALID") from err
    if effective>now.astimezone(KST).date():raise ValueError("FUTURE_SOURCE_DATE")
    source_age=(now.astimezone(KST).date()-effective).days
    if len(dated)-1!=int(cell(source[0],4)):
        raise ValueError("ETAX_MIRROR_ROW_COUNT_MISMATCH")
    indexed={}
    for row in dated[1:]:
        cms=cell(row,5);erp=cell(row,4)
        if not cms and not erp:raise ValueError("UNKEYED_DATED_ETAX_ROW")
        for kind,key in (("CMS",cms),("ERP",erp)):
            if not key:continue
            token=(kind,key)
            if token in indexed:raise ValueError("DUPLICATE_DATED_ETAX_IDENTIFIER")
            indexed[token]=row
    originals=original_qq(qq)
    checked=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    result=[]
    seen=set()
    for r in crosswalk[1:]:
        state=cell(r,4)
        if state not in ("DATED_ONLY_OR_UNRESOLVED_REVIEW","ID_AND_AMOUNT_MATCHED_SNAPSHOT_ONLY",
                         "BASE_ONLY_NOT_IN_DATED_SNAPSHOT","AMBIGUOUS_SNAPSHOT_MATCH",
                         "DUPLICATE_OR_CONFLICTING_ID_REVIEW","AMOUNT_NOT_COMPARABLE",
                         "ID_MATCH_AMOUNT_CONFLICT","NO_VERIFIABLE_INVOICE_KEY"):
            raise ValueError("UNKNOWN_CROSSWALK_STATE")
        if cell(r,7)!="NOT_VERIFIED":raise ValueError("UNEXPECTED_PAYMENT_APPROVAL")
        if state!="DATED_ONLY_OR_UNRESOLVED_REVIEW":continue
        kind,key=cell(r,0),cell(r,1)
        if kind not in ("ERP","CMS") or not key:raise ValueError("DATED_ONLY_KEY_MISSING")
        if (kind,key) in seen:raise ValueError("DUPLICATE_CROSSWALK_DATED_ONLY")
        seen.add((kind,key))
        row=indexed.get((kind,key))
        if row is None:raise ValueError("DATED_ONLY_NOT_IN_FEISHU_MIRROR")
        cms=cell(row,5)
        gross=amount(cell(row,15))
        bridge_gross=amount(cell(r,3))
        if gross is None or gross<=0 or gross!=bridge_gross:
            raise ValueError("DATED_ONLY_MIRROR_AMOUNT_CONFLICT")
        if cell(r,5)!=effective.isoformat():raise ValueError("CROSSWALK_MANIFEST_DATE_CONFLICT")
        qq_value=originals.get(cms) if cms else None
        if not cms:
            status="NO_CMS_IDENTIFIER_FOR_PERSONAL_QQ"
        elif qq_value is None:
            status="NOT_IN_PERSONAL_QQ_ORIGINALS"
        elif gross!=qq_value:
            status="QQ_ORIGINAL_GROSS_AMOUNT_CONFLICT"
        else:
            status="QQ_ORIGINAL_ID_AMOUNT_MATCHED"
        result.append([kind,key,cms,gross,qq_value if qq_value is not None else "",
            status,cell(row,25),effective.isoformat(),source_age,
            "NOT_VERIFIED",
            "No automatic income, owner, issue-date or payment confirmation",
            checked,""])
    if not result:raise ValueError("NO_DATED_ONLY_REVIEW")
    counts=dict(sorted(collections.Counter(r[5] for r in result).items()))
    stats={"dated_only_records":len(result),"qq_original_records":len(originals),
        "source_age_days":source_age,"states":counts,
        "revenue_writes":0,"payment_certifications":0,"ownership_certifications":0}
    return result,stats

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("CKD_DRIVE_SA_JSON","")
    run=os.getenv("GITHUB_RUN_ID","")
    if not raw or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_GITHUB_SHEETS_CONTEXT")
    cred=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    http=AuthorizedSession(cred)
    def req(method,url,**kw):
        resp=http.request(method,url,timeout=45,**kw)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    def read(book,title,range_):
        url=("https://sheets.googleapis.com/v4/spreadsheets/"+book+
             "/values/"+quote("'"+title+"'!"+range_,safe=""))
        return req("GET",url).get("values",[])
    sources={
      "crosswalk":read(BOOK,"Feishu eTax Base Sheet Crosswalk","A1:K5000"),
      "dated":read(BOOK,"Feishu Latest eTax","A1:AI5000"),
      "qq":read(QQ_BOOK,"CSS Tax Invoice Extract","A1:L10000"),
      "manifest":read(BOOK,"Feishu Source Manifest","A1:G12"),
    }
    rows,stats=audit(**sources,now=dt.datetime.now(KST))
    if len(rows)>1000:raise RuntimeError("REVIEW_ROW_LIMIT")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    meta=req("GET",url,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(p["properties"]["title"]==TAB for p in meta.get("sheets",[])):
        req("POST",url+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":1200,"columnCount":13,"frozenRowCount":1}}}}]})
    output=[HEAD]+[r[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for r in rows]
    loc=url+"/values/"+quote("'"+TAB+"'!A1:M"+str(len(output)),safe="")
    old=req("GET",loc).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("FOREIGN_REVIEW_TAB_HEADER")
    req("PUT",loc,params={"valueInputOption":"RAW"},json={"values":output})
    readback=req("GET",loc).get("values",[])
    if readback!=[[str(v) for v in r] for r in output]:
        raise RuntimeError("REVIEW_OUTPUT_READBACK_MISMATCH")
    print("FEISHU_ETAX_PERSONAL_QQ_COVERAGE="+json.dumps(stats,sort_keys=True))
    print("SOURCE_DATED_SNAPSHOT_REVIEW_ONLY;NO_VAT_ACTUAL_OR_PAYMENT_CHANGES")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FEISHU_ETAX_PERSONAL_QQ_AUDIT_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
