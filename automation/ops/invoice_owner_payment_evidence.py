#!/usr/bin/env python3
"""Exact-key sales-tag / bank-receipt candidate audit, NOT financial certification.

Source authority: QQ original invoice and exact matched Feishu snapshots.
A sales label is not a signed owner decision. A receipt row is not a verified
bank settlement. Never change customer mail, invoice Actual, or exclusion ledgers.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote

QQ="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
CSS="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TARGET="CSS Invoice Owner Payment Evidence"
HEAD=["Invoice No","QQ Month","Gross KRW (VAT incl)","AMEA Project","H Contract",
      "Feishu Exact CMS/Project","Feishu Sales Tag","Feishu Amount",
      "Receipt Exact Invoice/Amount","Receipt Candidate Count","Receipt Amount Match",
      "Source Outstanding Date","Source eTax Date","Source Receipt Date",
      "Owner Decision","Paid Decision","Revenue Treatment","Checked KST","GitHub Run"]
SELF="Kim Taehoon"
INVOICE=re.compile(r"\d{10,15}\Z")

def money(value):
    t=str(value or "").replace(",","").replace("₩","").strip()
    if t.upper().endswith(" KRW"):t=t[:-4].strip()
    if not re.fullmatch(r"\d+",t):raise ValueError("INVALID_GROSS_AMOUNT")
    return int(t)

def table(rows,fields):
    if not rows or any(k not in rows[0] for k in fields):
        raise ValueError("SOURCE_HEADER_UNEXPECTED")
    return [dict(zip(rows[0],r)) for r in rows[1:] if r]

def value(row,key):
    return str(row.get(key,"") or "").strip()

def classify(invoice, qq, out, etax, receipts, sources):
    no=value(invoice,"Invoice Number")
    if not INVOICE.fullmatch(no):raise ValueError("INVALID_REVIEW_INVOICE")
    original=qq.get(no)
    if not original:raise ValueError("QQ_INVOICE_NOT_FOUND")
    gross=money(value(original,"amount_krw"))
    if gross!=money(value(invoice,"Gross KRW (VAT incl)")):
        raise ValueError("GAP_SOURCE_AMOUNT_DRIFT")
    project=value(original,"amea_project_id")
    h=value(original,"h_project_id")
    if not re.fullmatch(r"AMEA\d{10}",project) or not re.fullmatch(r"H\d+SC\d+",h):
        raise ValueError("ORIGINAL_PROJECT_ID_INVALID")
    x="X"+h[1:]
    fs=[]
    for r in out:
        if value(r,"CMS Invoice Number")==no:
            fs.append(("out",r,value(r,"Project Number"),value(r,"Sales"),
                       value(r,"Invoice Amount")))
    for r in etax:
        if value(r,"CMS Invoice Num")==no:
            fs.append(("tax",r,value(r,"Project Number"),value(r,"Sales"),
                       value(r,"Amount")))
    source_matches=[]
    for scope,row,found_x,sales,amount in fs:
        if found_x!=x:
            raise ValueError("FEISHU_CONTRACT_CONFLICT")
        if scope=="tax" and value(row,"Quotation Number")!=project:
            raise ValueError("FEISHU_AMEA_CONFLICT")
        if money(amount)!=gross:
            raise ValueError("FEISHU_GROSS_CONFLICT")
        source_matches.append((scope,sales))
    tags={s.strip().casefold() for _,s in source_matches if s.strip()}
    if len(tags)>1:
        status="CONFLICTING_SALES_TAG_REVIEW"
    elif not tags:
        status="NO_FEISHU_SALES_TAG"
    elif tags=={SELF.casefold()}:
        status="SELF_TAGGED_UNCONFIRMED"
    else:
        status="OTHER_TAGGED_REVIEW"
    # Receipt mirror contains three independent horizontal panels. An exact
    # reference and amount only proves an entry exists, not a bank settlement.
    found=[]
    for r in receipts:
        for cms,amt,day in (("CMS No.","Amount (KRW)","Deposit Date"),
                            ("CMS No. [2]","Amount","Date"),
                            ("CMS No. [3]","Amount [2]","Date [2]")):
            if value(r,cms)==no:
                if not value(r,day):
                    raise ValueError("RECEIPT_DATE_MISSING")
                found.append(money(value(r,amt)))
    matched=sum(v==gross for v in found)
    if found and matched!=len(found):
        receipt="AMOUNT_CONFLICT_REVIEW"
    elif matched:
        receipt="EXACT_AMOUNT_CANDIDATE"
    else:
        receipt="NO_EXACT_RECEIPT_EVIDENCE"
    return [no,value(invoice,"Issue Month"),gross,project,h,
        "MATCH" if source_matches else "NOT_FOUND",
        status,"MATCH_GROSS" if source_matches else "NOT_CHECKED",
        receipt,len(found),"MATCH" if matched else ("CONFLICT" if found else "NOT_CHECKED"),
        sources["Payment Outstanding"],sources["eTax Invoice"],sources["Payment Receipt"],
        "NOT_VERIFIED","NOT_VERIFIED","DO_NOT_AUTO_ADD","",""]

def build(gaps,originals,out,etax,receipts,manifest):
    reviews=table(gaps,["Invoice Number","Issue Month","Gross KRW (VAT incl)"])
    qq=table(originals,["invoice_number","issued_month","amount_krw",
                        "amea_project_id","h_project_id"])
    original_map={value(r,"invoice_number"):r for r in qq}
    if len(original_map)!=len(qq):raise ValueError("DUPLICATE_QQ_ID")
    om=table(out,["CMS Invoice Number","Project Number","Sales","Invoice Amount"])
    tm=table(etax,["CMS Invoice Num","Project Number","Sales","Amount","Quotation Number"])
    rm=table(receipts,["CMS No.","Amount (KRW)","CMS No. [2]","Amount",
                       "CMS No. [3]","Amount [2]"])
    mm=table(manifest,["Source","Source Date","Source ID","Schema"])
    m={value(x,"Source"):x for x in mm}
    required=["Payment Outstanding","eTax Invoice","Payment Receipt"]
    for name in required:
        if name not in m or value(m[name],"Schema")!="HEADER_MATCHED":
            raise ValueError("FEISHU_SNAPSHOT_NOT_VALIDATED")
        if not re.fullmatch(r"20\d\d-\d\d-\d\d",value(m[name],"Source Date")):
            raise ValueError("FEISHU_SOURCE_DATE_MISSING")
    dates={k:value(m[k],"Source Date") for k in required}
    seen=set();outrows=[]
    for item in reviews:
        no=value(item,"Invoice Number")
        if no in seen:raise ValueError("DUPLICATE_GAP_REVIEW")
        seen.add(no)
        outrows.append(classify(item,original_map,om,tm,rm,dates))
    return outrows

def stats(rows):
    return {"review_count":len(rows),"sales_tags":dict(collections.Counter(r[6] for r in rows)),
       "receipt_evidence":dict(collections.Counter(r[8] for r in rows)),
       "gross_vat_inclusive":sum(r[2] for r in rows),
       "owner_certified":0,"paid_certified":0,"revenue_auto_booked":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.environ.get("CKD_DRIVE_SA_JSON","")
    if not raw:raise RuntimeError("NO_SHEETS_CREDENTIAL")
    session=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    def api(method,url,**kwargs):
        r=session.request(method,url,timeout=60,**kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}
    def read(book,ranges):
        endpoint="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values:batchGet"
        out=api("GET",endpoint,params=[("ranges",x) for x in ranges])
        ret=out.get("valueRanges",[])
        if len(ret)!=len(ranges):raise RuntimeError("INCOMPLETE_SHEETS_READ")
        return [v.get("values",[]) for v in ret]
    original=read(QQ,["'QQ 2026 Invoice Backfill'!A1:K1000"])[0]
    gaps,outstanding,etax,receipts,manifest=read(CSS,[
       "'CSS Invoice Gap Review'!A1:L100",
       "'Feishu Latest Outstanding'!A1:Q500",
       "'Feishu Latest eTax'!A1:AI200",
       "'Feishu Latest Receipts'!A1:Q700",
       "'Feishu Source Manifest'!A1:G15"])
    result=build(gaps,original,outstanding,etax,receipts,manifest)
    if not result:raise RuntimeError("NO_GAP_REVIEW_ROWS")
    run=os.environ.get("GITHUB_RUN_ID","")
    if not run.isdigit() or os.environ.get("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("INVALID_GITHUB_RUN")
    url="https://github.com/kimtk94/Codex/actions/runs/"+run
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    rows=[HEAD]+[r[:-2]+[now,url] for r in result]
    base="https://sheets.googleapis.com/v4/spreadsheets/"+CSS
    meta=api("GET",base+"?fields=sheets.properties(title,sheetId)")
    found=[s for s in meta.get("sheets",[]) if s.get("properties",{}).get("title")==TARGET]
    if not found:
        api("POST",base+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TARGET,"gridProperties":{"rowCount":100,"columnCount":19,
            "frozenRowCount":1}}}}]})
    a1=lambda area:base+"/values/"+quote("'"+TARGET+"'!"+area,safe="")
    existing=api("GET",a1("A1:S100")).get("values",[])
    if existing and existing[0]!=HEAD:raise RuntimeError("REVIEW_SHEET_HEADER_CHANGED")
    end=max(len(rows),len(existing))
    if end>100:raise RuntimeError("REVIEW_TOO_LARGE")
    padded=rows+[[""]*len(HEAD) for _ in range(end-len(rows))]
    api("PUT",a1("A1:S"+str(end))+"?valueInputOption=RAW",json={"values":padded})
    readback=api("GET",a1("A1:S"+str(len(rows)))).get("values",[])
    if len(readback)!=len(rows) or readback[0]!=HEAD or any(
            [str(x) for x in got[:17]]!=[str(x) for x in expected[:17]]
            for got,expected in zip(readback[1:],rows[1:])):
        raise RuntimeError("OWNER_PAYMENT_REVIEW_READBACK_MISMATCH")
    print("CSS_OWNER_PAYMENT_REVIEW="+json.dumps(stats(result),sort_keys=True))
    print("READ_ONLY_SOURCE;GENERATED_SHEET_ONLY;OWNER_NOT_VERIFIED;PAID_NOT_VERIFIED")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_OWNER_PAYMENT_REVIEW_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
