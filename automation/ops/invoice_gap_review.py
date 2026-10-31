#!/usr/bin/env python3
"""Publish a generated cross-source invoice *review* list, never book Revenue.

QQ original invoice evidence is not proof that an invoice belongs to this
salesperson. CSS Extract existence alone never authorizes an Actual addition.
Only the generated 'CSS Invoice Gap Review' tab may be changed.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

QQ = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
CSS = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "CSS Invoice Gap Review"
HEAD = ["Invoice Number","Issue Month","Gross KRW (VAT incl)",
        "QQ Original Evidence","CSS Canonical","CSS Extract",
        "Extract Amount Parity","Review Classification","Owner Verified",
        "Revenue Treatment","Verified KST","GitHub Run"]
INVOICE = re.compile(r"\d{10,15}\Z")

def record_map(rows, number, amount, month=None):
    if not rows or any(k not in rows[0] for k in
                       ((number,amount,month) if month else (number,amount))):
        raise ValueError("INVOICE_GAP_SOURCE_SCHEMA_CHANGED")
    idx={x:i for i,x in enumerate(rows[0])}
    found={}
    for r in rows[1:]:
        if not r: continue
        invoice=str(r[idx[number]]).strip() if idx[number]<len(r) else ""
        if not invoice: continue
        if not INVOICE.fullmatch(invoice):
            raise ValueError("INVALID_INVOICE_NUMBER")
        raw=str(r[idx[amount]]).replace(",","").strip() if idx[amount]<len(r) else ""
        if not raw.isdigit():
            raise ValueError("INVALID_INVOICE_AMOUNT")
        gross=int(raw)
        if gross<=0: raise ValueError("NONPOSITIVE_INVOICE_AMOUNT")
        mm=str(r[idx[month]]).strip() if month and idx[month]<len(r) else ""
        if month and mm and not mm.startswith("2026-"):
            continue
        if month and not re.fullmatch(r"2026-(0[1-9]|1[0-2])",mm):
            raise ValueError("INVALID_INVOICE_MONTH")
        if invoice in found and found[invoice]["gross"]!=gross:
            raise ValueError("CONFLICTING_INVOICE_AMOUNT")
        if invoice in found:
            continue
        found[invoice]={"gross":gross,"month":mm,"row":r,"index":idx}
    return found

def text_at(item,field):
    if not item:return ""
    j=item["index"].get(field,-1)
    return str(item["row"][j]).strip() if 0<=j<len(item["row"]) else ""

def review(qq_rows,canonical_rows,extract_rows):
    qq=record_map(qq_rows,"invoice_number","amount_krw","issued_month")
    canonical=record_map(canonical_rows,"invoice_number","amount_krw","invoice_month")
    extracted=record_map(extract_rows,"invoice_number","amount_krw")
    if not qq or not canonical:
        raise ValueError("MISSING_BASELINE_INVOICE_EVIDENCE")
    differences=sorted(set(qq)^set(canonical))
    out=[]
    for invoice in differences:
        q,c,e=qq.get(invoice),canonical.get(invoice),extracted.get(invoice)
        if q and e and q["gross"]!=e["gross"]:
            raise ValueError("EXTRACT_AMOUNT_CONFLICT")
        if q and c:
            raise ValueError("UNREACHABLE_ALREADY_CANONICAL")
        if q and e:
            state="CSS_EXTRACT_PRESENT_CANONICAL_MISSING"
            parity="MATCH_GROSS"
        elif q:
            state="QQ_ONLY_CSS_EXTRACT_MISSING"
            parity="NOT_CHECKED"
        else:
            state="CSS_CANONICAL_ONLY_QQ_MISSING"
            parity="NOT_CHECKED"
        item=q or c
        out.append([invoice,item["month"],item["gross"],
                    text_at(q,"evidence") if q else "NOT_IN_QQ",
                    "PRESENT" if c else "NOT_IN_CANONICAL",
                    text_at(e,"validation_status") or ("PRESENT" if e else "NOT_FOUND"),
                    parity,state,"NOT_VERIFIED","DO_NOT_AUTO_ADD","",""])
    return out

def summary(rows):
    groups=collections.Counter(r[7] for r in rows)
    return {"gap_count":len(rows),"by_class":dict(sorted(groups.items())),
            "gross_krw_vat_included":sum(r[2] for r in rows),
            "ownership_verified":False,"revenue_auto_added":False}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.environ.get("CKD_DRIVE_SA_JSON","")
    if not raw: raise RuntimeError("MISSING_SHEETS_CREDENTIAL")
    client=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    def request(method,url,**kwargs):
        resp=client.request(method,url,timeout=65,**kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    def ranges(book,items):
        url="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values:batchGet"
        params=[("ranges",name) for name in items]+[("valueRenderOption","FORMATTED_VALUE")]
        result=request("GET",url,params=params).get("valueRanges",[])
        if len(result)!=len(items):raise RuntimeError("INCOMPLETE_SOURCE_READ")
        return [v.get("values",[]) for v in result]
    qq,canonical,extract=ranges(QQ,[
        "'QQ 2026 Invoice Backfill'!A1:K1000",
        "'CSS Tax Invoice List'!A1:N1000",
        "'CSS Tax Invoice Extract'!A1:L1000"])
    table=review(qq,canonical,extract)
    stamp=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    run=os.environ.get("GITHUB_RUN_ID","")
    if not run.isdigit() or os.environ.get("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("INVALID_GITHUB_RUN_CONTEXT")
    url="https://github.com/kimtk94/Codex/actions/runs/"+run
    table=[r[:-2]+[stamp,url] for r in table]
    base="https://sheets.googleapis.com/v4/spreadsheets/"+CSS
    meta=request("GET",base+"?fields=sheets.properties(title,sheetId,gridProperties.rowCount)")
    sheets=[z["properties"] for z in meta.get("sheets",[]) if z["properties"]["title"]==TAB]
    if not sheets:
        request("POST",base+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":500,"columnCount":12,"frozenRowCount":1}}}}]})
    area=urllib.parse.quote("'"+TAB+"'!A1:L500",safe="")
    endpoint=base+"/values/"+area
    previous=request("GET",endpoint).get("values",[])
    if previous and previous[0]!=HEAD:
        raise RuntimeError("REFUSE_FOREIGN_REVIEW_TAB")
    max_rows=max(len(previous),len(table)+1)
    if max_rows>500:raise RuntimeError("REVIEW_TAB_TOO_MANY_ROWS")
    values=[HEAD]+table+[[""]*len(HEAD) for _ in range(max_rows-len(table)-1)]
    target=urllib.parse.quote("'"+TAB+"'!A1:L"+str(max_rows),safe="")
    request("PUT",base+"/values/"+target+"?valueInputOption=RAW",json={"values":values})
    back=request("GET",base+"/values/"+target).get("values",[])
    if not back or back[0]!=HEAD or len(back)<len(table)+1 or any(
          [str(v) for v in back[i+1][:10]]!=[str(v) for v in row[:10]]
          for i,row in enumerate(table)):
        raise RuntimeError("INVOICE_REVIEW_READBACK_MISMATCH")
    print("CSS_INVOICE_GAP_REVIEW_PUBLISHED "+json.dumps(summary(table),sort_keys=True))
    print("ORIGINAL_REVENUE_UNCHANGED;OWNER_NOT_VERIFIED;REVIEW_TAB_ONLY")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_INVOICE_GAP_REVIEW_FAILED="+type(exc).__name__+":"+str(exc)[:100],file=sys.stderr)
        sys.exit(1)
