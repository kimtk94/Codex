#!/usr/bin/env python3
"""Sync original verified QQ TAX INVOICE evidence to the central source.

QQ extraction must complete successfully first. Append-only: never rewrite
existing invoice/source rows, approved service classifications or decisions.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

KST=dt.timezone(dt.timedelta(hours=9))
QQ=os.getenv("QQ_CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
BI=os.getenv("BI_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
SOURCE="CSS Tax Invoice Extract"
TARGET="CSS Tax Invoices"
STATUS={"FILENAME_PARSED","EXISTS_IN_LEGACY","VERIFIED_LEGACY_FILENAME"}
NOTICE=re.compile(r"^\s*(?:❗\ufe0f?\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY=re.compile(r"^\s*(?:Re|Fw|Fwd|회신|답장|전달)\s*[:：]",re.I)
NUMBER=re.compile(r"^\d{12}$")
FILENAME=re.compile(r"TAX\s+INVOICE-(\d{12})-.*-KRW(\d+)(?:\.00)?\.pdf$",re.I)
HEAD=["invoice_month","issued_at","invoice_number","amount_krw","project_id",
      "h_project_number","po_reference","institution","service","project_description",
      "attachment_filename","subject","uid","source_row","source_ingest_key"]


def cell(r,i):
    return str(r[i]).strip() if i<len(r) and r[i] is not None else ""


def amount(value):
    clean=re.sub(r"[,\s₩]","",str(value)).removesuffix("KRW")
    if not re.fullmatch(r"\d+(?:\.0+)?",clean):
        raise RuntimeError("INVOICE_AMOUNT_NOT_INTEGER")
    n=int(float(clean))
    if n<=0:raise RuntimeError("INVOICE_AMOUNT_NONPOSITIVE")
    return n


def original_record(r):
    if len(r)<12:raise RuntimeError("QQ_INVOICE_EVIDENCE_INCOMPLETE")
    invoice=cell(r,0)
    if not NUMBER.fullmatch(invoice):raise RuntimeError("QQ_INVOICE_ID_INVALID")
    subject=cell(r,6)
    if not NOTICE.match(subject) or REPLY.match(subject):
        raise RuntimeError("QQ_INVOICE_NONORIGINAL_NOTICE")
    if cell(r,10) not in STATUS:raise RuntimeError("QQ_INVOICE_NOT_VERIFIED")
    amt=amount(cell(r,1))
    filename=re.sub(r"\s+"," ",cell(r,5))
    match=FILENAME.search(filename)
    if not match or match.group(1)!=invoice or int(match.group(2))!=amt:
        raise RuntimeError("QQ_INVOICE_FILENAME_AMOUNT_CONFLICT")
    amea,h=cell(r,2),cell(r,3)
    if not amea or not h or amea not in subject or h not in subject:
        raise RuntimeError("QQ_INVOICE_PROJECT_ID_CONFLICT")
    uid=cell(r,8)
    ingest=cell(r,9)
    if not re.fullmatch(r"\d+",uid) or not ingest.endswith("|"+uid):
        raise RuntimeError("QQ_INVOICE_SOURCE_UID_INVALID")
    date=dt.datetime.fromisoformat(cell(r,7).replace("Z","+00:00"))
    if date.tzinfo is None:raise RuntimeError("QQ_INVOICE_TIMEZONE_MISSING")
    local=date.astimezone(KST)
    subject_project=re.search(r"(Korea-.*)-"+re.escape(amea)+r"$",subject,re.I)
    if not subject_project:raise RuntimeError("QQ_INVOICE_PROJECT_DESCRIPTION_MISSING")
    desc=subject_project.group(1)
    institution=(re.search(r"^Korea-(.+?)-\d+-",desc,re.I) or [None,"UNCLASSIFIED"])[1]
    service=("PMP" if re.search(r"\bPMP\b",desc,re.I) else
             "Proteomics" if re.search(r"Deep.?DIA|proteom",desc,re.I) else
             "mRNA-Seq" if re.search(r"mRNA|RNA.?Seq",desc,re.I) else
             "Amplicon" if re.search(r"16S|amplicon",desc,re.I) else
             "WGS" if re.search(r"WGS|WES",desc,re.I) else
             "Metabolomics" if re.search(r"Metabolom",desc,re.I) else "Other")
    return [local.strftime("%Y-%m"),local.strftime("%Y-%m-%d %H:%M:%S"),
            invoice,f"{amt:,} KRW",amea,h,cell(r,4),institution,service,
            desc,filename,subject,"inbox:"+uid,"",ingest]


def plan(qq,central):
    if not qq or qq[0][:2]!=["invoice_number","amount_krw"]:
        raise RuntimeError("QQ_INVOICE_SCHEMA_INVALID")
    if not central or central[0][:12]!=HEAD[:12] or central[0][14]!=HEAD[14]:
        raise RuntimeError("CENTRAL_INVOICE_SCHEMA_INVALID")
    existing={}
    for row in central[1:]:
        if not cell(row,2):continue
        invoice=cell(row,2)
        if invoice in existing:raise RuntimeError("CENTRAL_DUPLICATE_INVOICE")
        existing[invoice]=amount(cell(row,3))
    if not existing:raise RuntimeError("CENTRAL_SOURCE_EMPTY")
    originals={}
    for record in qq[1:]:
        if not record or not cell(record,0):continue
        parsed=original_record(record)
        invoice=parsed[2]
        if invoice in originals:
            if originals[invoice][3]!=parsed[3] or originals[invoice][14]!=parsed[14]:
                raise RuntimeError("QQ_DUPLICATE_ORIGINAL_CONFLICT")
            continue
        originals[invoice]=parsed
    if not originals:raise RuntimeError("NO_VERIFIED_QQ_INVOICES")
    pending=[]
    for invoice,row in originals.items():
        gross=amount(row[3])
        if invoice in existing:
            if existing[invoice]!=gross:raise RuntimeError("QQ_CENTRAL_AMOUNT_MISMATCH")
        else:
            pending.append(row)
    return pending,len(originals),len(existing)


def api(session,method,spreadsheet,path,**kwargs):
    root="https://sheets.googleapis.com/v4/spreadsheets/"+spreadsheet
    response=session.request(method,root+path,timeout=75,**kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def sheet_read(session,book,tab,area):
    a1=urllib.parse.quote("'"+tab+"'!"+area,safe="")
    return api(session,"GET",book,"/values/"+a1).get("values",[])


def main():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    cred=service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session=AuthorizedSession(cred)
    qq=sheet_read(session,QQ,SOURCE,"A1:L2500")
    central=sheet_read(session,BI,TARGET,"A1:O2000")
    new,verified,old=plan(qq,central)
    print(f"QQ_CENTRAL_INVOICE_PREFLIGHT verified={verified} existing={old} new={len(new)}")
    if not new:
        print("QQ_CENTRAL_INVOICE_SYNC_PASS no_new_invoice=1")
        return
    meta=api(session,"GET",BI,"?fields=sheets.properties(sheetId,title,gridProperties(rowCount))")
    props={x["properties"]["title"]:x["properties"] for x in meta.get("sheets",[])}
    if TARGET not in props:raise RuntimeError("CENTRAL_SOURCE_TAB_MISSING")
    sid=props[TARGET]["sheetId"]
    last=max((i for i,r in enumerate(central) if i>0 and cell(r,2)),default=0)
    next_row=last+1
    capacity=props[TARGET].get("gridProperties",{}).get("rowCount",0)
    if not capacity:raise RuntimeError("CENTRAL_SOURCE_GRID_UNKNOWN")
    requests=[]
    overflow=max(0,next_row+len(new)-capacity)
    if overflow:
        requests.append({"appendDimension":{"sheetId":sid,"dimension":"ROWS","length":overflow}})
    def gs(v):
        return {"userEnteredValue":{"stringValue":str(v)}}
    requests.append({"updateCells":{
        "start":{"sheetId":sid,"rowIndex":next_row,"columnIndex":0},
        "rows":[{"values":[gs(v) for v in row]} for row in new],
        "fields":"userEnteredValue"}})
    # The final check is mandatory. On partial failure a rerun is idempotent.
    api(session,"POST",BI,":batchUpdate",json={"requests":requests})
    observed=sheet_read(session,BI,TARGET,"A"+str(next_row+1)+":O"+str(next_row+len(new)))
    if len(observed)!=len(new) or any(cell(a,2)!=b[2] or amount(cell(a,3))!=amount(b[3])
                                      or cell(a,14)!=b[14] for a,b in zip(observed,new)):
        raise RuntimeError("CENTRAL_INVOICE_POSTWRITE_PARITY_FAILED")
    print(f"QQ_CENTRAL_INVOICE_SYNC_PASS appended={len(new)} gross_krw={sum(amount(x[3]) for x in new)}")


if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("QQ_CENTRAL_INVOICE_SYNC_FAILED "+type(exc).__name__+":"+str(exc)[:160],file=sys.stderr)
        sys.exit(1)
