#!/usr/bin/env python3
"""Audit Feishu manual eTax vs quote forecast without claiming issuance.

Reads only sanitized Feishu mirrors and generated personal QQ evidence.
Writes only CSS Manual eTax Quote Review. Does not mutate Revenue, unissued
forecast, original Feishu, Lead decisions, Salesforce or payment status.
"""
import collections
import datetime as dt
import json
import os
import sys
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import quote
from zoneinfo import ZoneInfo

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS Manual eTax Quote Review"
KST=ZoneInfo("Asia/Seoul")
HEAD=["AMEA","ERP Invoice Number","Feishu Gross KRW VAT incl",
      "Grouped Gross KRW VAT incl","Grouped Net KRW VAT excl",
      "Watch Quote KRW","Net minus Quote KRW",
      "Unissued Watch Matched Invoice Count","Candidate State",
      "Feishu Sales Label (not certified owner)","Snapshot Date",
      "Source / approval boundary","Payment/Issuance Decision",
      "Checked KST","GitHub Run"]
PERSONAL_SALES_LABEL="Kim Taehoon"

def cell(row,index):
    return str(row[index]).strip() if isinstance(row,list) and len(row)>index and row[index] is not None else ""

def money(raw):
    raw=str(raw or "").replace(",","").replace("₩","").replace(" KRW","").strip()
    if not raw.isdigit():raise ValueError("NON_INTEGER_MONEY")
    return int(raw)

def net(gross):
    return int((Decimal(gross)*Decimal(10)/Decimal(11)).quantize(
        Decimal("1"),rounding=ROUND_HALF_UP))

def audit(dated,personal,unissued,manifest,now):
    if now.tzinfo is None:raise ValueError("NAIVE_TIMESTAMP")
    if not dated or [cell(dated[0],i) for i in (2,3,4,5,10,15,25)]!=[
        "Source","Type","ERP Invoice Number","CMS Invoice Num","Quotation Number",
        "Amount","Sales"]:
        raise ValueError("FEISHU_ETAX_SCHEMA_DRIFT")
    if not personal or [cell(personal[0],i) for i in (0,1,5,9)]!=[
        "Source Key Type","Feishu Invoice Key","Personal QQ Evidence","Finance Decision"]:
        raise ValueError("PERSONAL_QQ_COVERAGE_SCHEMA_DRIFT")
    if not unissued or [cell(unissued[0],i) for i in (0,4,6,10)]!=[
        "AMEA Project ID","Quote KRW","Matched Invoice Count","Review Status"]:
        raise ValueError("UNISSUED_WATCH_SCHEMA_DRIFT")
    if not manifest or [cell(manifest[0],i) for i in (0,1)]!=["Source","Source Date"]:
        raise ValueError("MANIFEST_SCHEMA_DRIFT")
    etax=[row for row in manifest[1:] if cell(row,0)=="eTax Invoice"]
    if len(etax)!=1:raise ValueError("ETAX_SOURCE_DATE_MISSING_OR_AMBIGUOUS")
    stamp=cell(etax[0],1)
    try:source_date=dt.date.fromisoformat(stamp)
    except ValueError as e:raise ValueError("SOURCE_DATE_INVALID") from e
    if source_date>now.astimezone(KST).date():raise ValueError("SOURCE_DATE_FUTURE")
    if int(cell(etax[0],4))!=len(dated)-1:
        raise ValueError("ETAX_SOURCE_ROW_COUNT_DRIFT")
    byERP={}
    for row in dated[1:]:
        erp=cell(row,4)
        if not erp:raise ValueError("DATED_ETAX_ERP_MISSING")
        if erp in byERP:raise ValueError("DATED_ETAX_ERP_DUPLICATE")
        byERP[erp]=row
    watch={}
    for row in unissued[1:]:
        amea=cell(row,0)
        if not amea:continue
        if amea in watch:raise ValueError("DUPLICATE_UNISSUED_WATCH_AMEA")
        watch[amea]=row
    selected=[]
    for row in personal[1:]:
        if cell(row,5)!="MANUAL_INVOICE_NO_CMS_QQ_UNPROVEN":continue
        if cell(row,9)!="NOT_VERIFIED":
            raise ValueError("UNAPPROVED_PERSONAL_FINANCE_DECISION")
        erp=cell(row,1)
        if cell(row,0)!="ERP" or not erp or cell(row,2):
            raise ValueError("MANUAL_NO_CMS_INCONSISTENT")
        dated_row=byERP.get(erp)
        if dated_row is None:raise ValueError("PERSONAL_MANUAL_ERP_NOT_IN_ETAX")
        if cell(dated_row,5) or cell(dated_row,2)!="Manual Invoice":
            raise ValueError("MANUAL_SOURCE_NOT_PROVEN")
        if cell(dated_row,25)!=PERSONAL_SALES_LABEL:continue
        if money(cell(row,3))!=money(cell(dated_row,15)):
            raise ValueError("PERSONAL_MANUAL_AMOUNT_CONFLICT")
        if cell(row,7)!=stamp:raise ValueError("PERSONAL_MANUAL_SNAPSHOT_DRIFT")
        amea=cell(dated_row,10)
        if not amea.startswith("AMEA"):raise ValueError("MANUAL_PROJECT_AMEA_MISSING")
        selected.append((amea,erp,money(cell(dated_row,15)),cell(dated_row,25)))
    if not selected:raise ValueError("NO_PERSONAL_MANUAL_CANDIDATES")
    if len({erp for _,erp,_,_ in selected})!=len(selected):
        raise ValueError("DUPLICATE_PERSONAL_MANUAL_ERP")
    groups=collections.defaultdict(list)
    for tup in selected:groups[tup[0]].append(tup)
    generated=[]
    at=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    stats={"manual_candidates":len(selected),"projects":len(groups),
           "quote_amount_candidate_projects":0,"gross_sum":sum(x[2] for x in selected),
           "source_date":stamp,"source_age_days":(now.astimezone(KST).date()-source_date).days,
           "revenue_changes":0,"payment_approvals":0,"issued_certifications":0}
    for amea,entries in sorted(groups.items()):
        gross=sum(x[2] for x in entries)
        group_net=net(gross)
        watch_row=watch.get(amea)
        quote_amount=money(cell(watch_row,4)) if watch_row else None
        matched=cell(watch_row,6) if watch_row else ""
        if watch_row and cell(watch_row,10)!="ISSUANCE_NOT_VERIFIED":
            raise ValueError("UNISSUED_WATCH_DECISION_CHANGED")
        delta=group_net-quote_amount if quote_amount is not None else None
        if quote_amount is None:
            status="QUOTE_WATCH_NOT_FOUND_REVIEW"
        elif matched!="0":
            status="ALREADY_MATCHED_WATCH_MANUAL_EVIDENCE_REVIEW"
        elif abs(delta)<=10:
            status="NET_QUOTE_AMOUNT_CANDIDATE_NO_ISSUANCE_PROOF"
            stats["quote_amount_candidate_projects"]+=1
        else:
            status="AMOUNT_OR_SPLIT_MISMATCH_REVIEW"
        for _,erp,invoice_gross,sales in sorted(entries):
            generated.append([amea,erp,invoice_gross,gross,group_net,
                quote_amount if quote_amount is not None else "",
                delta if delta is not None else "",matched,status,sales,stamp,
                "Manual ERP record and 5-day-old eTax snapshot; request invoice PDF + issuance confirmation",
                "NOT_VERIFIED",at,""])
    return generated,stats

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("CKD_DRIVE_SA_JSON","")
    run=os.getenv("GITHUB_RUN_ID","")
    if not raw or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_SOURCE")
    creds=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client=AuthorizedSession(creds)
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def request(method,url,**kwargs):
        resp=client.request(method,url,timeout=55,**kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    def read(sheet,range_):
        return request("GET",root+"/values/"+quote("'"+sheet+"'!"+range_,safe="")).get("values",[])
    data={
        "dated":read("Feishu Latest eTax","A1:AI500"),
        "personal":read("Feishu eTax Personal QQ Coverage","A1:M1200"),
        "unissued":read("Unissued Invoice Watch","A1:O1000"),
        "manifest":read("Feishu Source Manifest","A1:G12"),
    }
    rows,stats=audit(**data,now=dt.datetime.now(KST))
    if len(rows)>500:raise RuntimeError("GENERATED_MANUAL_ROWS_TOO_MANY")
    metadata=request("GET",root,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(x.get("properties",{}).get("title")==TAB for x in metadata.get("sheets",[])):
        request("POST",root+":batchUpdate",json={"requests":[{"addSheet":{
            "properties":{"title":TAB,"gridProperties":{
                "rowCount":700,"columnCount":len(HEAD),"frozenRowCount":1}}}}]})
    output=[HEAD]+[r[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for r in rows]
    locator=root+"/values/"+quote("'"+TAB+"'!A1:O"+str(len(output)),safe="")
    old=request("GET",locator).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("FOREIGN_GENERATED_REVIEW_TAB")
    clear=root+"/values/"+quote("'"+TAB+"'!A1:O700",safe="")+":clear"
    request("POST",clear,json={})
    request("PUT",locator,params={"valueInputOption":"RAW"},json={"values":output})
    back=request("GET",locator).get("values",[])
    if back!=[[str(x) for x in row] for row in output]:
        raise RuntimeError("MANUAL_ETAX_QUOTE_READBACK_MISMATCH")
    print("CSS_MANUAL_ETAX_QUOTE_REVIEW="+json.dumps(stats,sort_keys=True))
    print("NO_AUTO_REVENUE,NO_MANUAL_ISSUANCE_CERTIFICATION,NO_BANK_PAYMENT_CERTIFICATION")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_MANUAL_ETAX_QUOTE_REVIEW_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
