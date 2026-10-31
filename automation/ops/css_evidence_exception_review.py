#!/usr/bin/env python3
"""Source freshness/legacy coverage exceptions in a generated review-only tab.

A successful GitHub Action means the inspection ran, not that data is complete.
Never mutate invoice originals, owner decisions, finance Actual, SFDC or Vercel.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import time
from urllib.parse import quote

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS Evidence Exception Review"
KST=dt.timezone(dt.timedelta(hours=9))
HEAD=["Area","Check","Evidence State","Source","Expected","Observed",
      "Evidence Timestamp","Checked KST","Review Boundary","GitHub Run"]
SOURCES={
 "net":("'BI Revenue Net VAT Monthly'!A1:I24","Month"),
 "legacy":("'Tax Invoice Completeness Audit'!A1:C25","TAX INVOICE COMPLETENESS AUDIT"),
 "feishu":("'Feishu Source Manifest'!A1:G10","Source"),
 "gap":("'CSS Invoice Gap Review'!A1:L100","Invoice Number"),
 "owner":("'CSS Invoice Owner Payment Evidence'!A1:S100","Invoice No"),
 "accept":("'CSS Operational Acceptance'!A1:H20","Area"),
 "mail":("'CSS Mail Backfill Status'!A1:O3","Updated At KST"),
}

def cell(r,i):
    return str(r[i] or "").strip() if r is not None and i<len(r) else ""

def n(value):
    raw=str(value or "").replace(",","").replace("₩","").replace(" KRW","").strip()
    if not re.fullmatch(r"\d+",raw):raise ValueError("INVALID_MONEY_COUNT")
    return int(raw)

def date(value):
    try:return dt.date.fromisoformat(str(value))
    except (ValueError,TypeError):return None

def timestamp(text):
    raw=str(text or "").strip()
    if not raw:return None
    try:
        if raw.endswith(" KST"):
            return dt.datetime.strptime(raw,"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
        found=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        return found if found.tzinfo else None
    except ValueError:return None

def analyze(data,now):
    if now.tzinfo is None:raise ValueError("NAIVE_NOW")
    today=now.astimezone(KST).date()
    for name,(_,head) in SOURCES.items():
        rows=data.get(name)
        if not rows or cell(rows[0],0)!=head:raise ValueError("SOURCE_SCHEMA_"+name.upper())
    output=[]
    def add(area,check,state,source,expected,observed,evidence,boundary):
        if state not in ("PASS","REVIEW","BLOCK"):raise ValueError("INVALID_EVIDENCE_STATE")
        output.append([area,check,state,source,str(expected),str(observed),
            str(evidence or ""),now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
            boundary,""])
    net=data["net"]
    month=today.strftime("%Y-%m")
    row=next((r for r in net[1:] if cell(r,0)==month),None)
    if row is None:raise ValueError("CURRENT_NET_MONTH_MISSING")
    gross,net_krw,count=n(cell(row,1)),n(cell(row,2)),n(cell(row,4))
    last=timestamp(cell(row,7))
    valid=(gross*10==net_krw*11 and count>0 and
           cell(row,8)=="INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED")
    recent=bool(last and 0<=(now-last).total_seconds()<=8*3600)
    add("Revenue","Canonical VAT-exclusive issued", "PASS" if valid and recent else "BLOCK",
        "BI Revenue Net VAT Monthly", "VAT incl = issued net x 1.1; updated <=8h",
        "count="+str(count)+";gross="+str(gross)+";net="+str(net_krw),
        cell(row,7),"Forecast excluded; payment and ownership not certified")

    legacy=data["legacy"]
    values={cell(r,0):cell(r,1) for r in legacy[1:] if cell(r,0)}
    for k in ("October invoice count","October invoice amount KRW","Invoice source last date"):
        if k not in values:raise ValueError("LEGACY_AUDIT_FIELD_MISSING")
    old_count=n(values["October invoice count"])
    old_gross=n(values["October invoice amount KRW"])
    equal=old_count==count and old_gross==gross
    add("Revenue","Legacy October coverage parity","PASS" if equal else "REVIEW",
        "Tax Invoice Completeness Audit","Match canonical scope or mark legacy non-authoritative",
        "legacy_count="+str(old_count)+";canonical_count="+str(count)+
          ";legacy_gross="+str(old_gross)+";canonical_gross="+str(gross),
        values["Invoice source last date"],
        "Different source scopes possible; never add legacy amount to Actual")
    old_date=date(values["Invoice source last date"])
    age=(today-old_date).days if old_date else None
    add("Revenue","Legacy invoice source recency",
        "PASS" if age is not None and 0<=age<=2 else "REVIEW",
        "Tax Invoice Completeness Audit","Source issue date <=2 calendar days",
        "source_age_days="+str(age if age is not None else "UNKNOWN"),
        values["Invoice source last date"],
        "Source latest date is not a sync timestamp; pending coverage review")

    feishu=data["feishu"]
    required=("Payment Outstanding","eTax Invoice","Payment Receipt","Prepayments","Online-Project")
    by={cell(r,0):r for r in feishu[1:] if cell(r,0)}
    if any(x not in by for x in required):raise ValueError("FEISHU_SOURCE_MISSING")
    dates={x:date(cell(by[x],1)) for x in required}
    stale=[x for x in required[:4] if dates[x] is None or (today-dates[x]).days>2
           or (today-dates[x]).days<0]
    add("Feishu","Payment source effective date","REVIEW" if stale else "PASS",
        "Feishu Source Manifest","All four payment sources <=2 calendar days old",
        "stale_count="+str(len(stale))+";effective_dates="+
          ",".join(sorted(set(str(cell(by[x],1)) for x in required[:4]))),
        cell(by["Payment Receipt"],2),
        "Successful mirror sync is not a new original receipt; no paid certification")
    online=dates["Online-Project"]
    online_delta=(today-online).days if online else None
    add("Feishu","Project status original date",
        "PASS" if online_delta is not None and 0<=online_delta<=1 else "REVIEW",
        "Feishu Source Manifest","Online project original <=1 calendar day",
        "source_age_days="+str(online_delta),cell(by["Online-Project"],2),
        "Forecast is not recognized issued revenue")

    gaps=data["gap"][1:]
    owners=data["owner"][1:]
    ids={cell(r,0) for r in gaps}
    if not ids or len(ids)!=len(gaps) or any(not re.fullmatch(r"\d{10,15}",key) for key in ids):
        raise ValueError("GAP_KEYS_INVALID")
    owner_ids={cell(r,0) for r in owners}
    if owner_ids!=ids or len(owners)!=len(ids):raise ValueError("GAP_OWNER_KEYS_DIFFER")
    if any(cell(r,8)!="NOT_VERIFIED" or cell(r,9)!="DO_NOT_AUTO_ADD" for r in gaps):
        raise ValueError("UNAPPROVED_INVOICE_REVENUE_CHANGE")
    if any(cell(r,14)!="NOT_VERIFIED" or cell(r,15)!="NOT_VERIFIED"
           or cell(r,16)!="DO_NOT_AUTO_ADD" for r in owners):
        raise ValueError("UNAPPROVED_OWNER_PAYMENT_CHANGE")
    gross_gap=sum(n(cell(r,2)) for r in gaps)
    add("Invoice","Canonical gap and owner hold","REVIEW",
        "CSS Invoice Gap Review + Owner Payment Evidence",
        "0 unresolved or explicitly owner+finance-approved",
        "unresolved="+str(len(gaps))+";vat_gross_krw="+str(gross_gap),
        cell(gaps[0],10),"All rows DO_NOT_AUTO_ADD; invoice evidence not personal Revenue")
    receipt_candidates=sum(cell(r,8)=="EXACT_AMOUNT_CANDIDATE" for r in owners)
    add("Payment","Receipt candidate versus paid certification","REVIEW",
        "CSS Invoice Owner Payment Evidence",
        "Bank remittance verified per invoice (not just CMS/amount)",
        "receipt_candidates="+str(receipt_candidates)+";paid_certified=0",
        cell(owners[0],17),"Candidate matching does not establish deposit or settlement")

    accept=data["accept"]
    if [cell(accept[0],i) for i in range(4)]!=["Area","Check","Result","Gate"]:
        raise ValueError("ACCEPTANCE_HEADER_INVALID")
    approvals={cell(r,1):r for r in accept[1:] if cell(r,1)}
    release_keys=("Owner-authenticated Preview E2E","Production READY SHA parity","Production acceptance")
    if any(k not in approvals for k in release_keys):
        raise ValueError("RELEASE_GATE_MISSING")
    release_ok=all(cell(approvals[k],2)=="PASS" for k in release_keys)
    add("Web","Production/owner browser release gate",
        "REVIEW" if not release_ok else "PASS","CSS Operational Acceptance",
        "Release gates PASS plus explicit owner approval",
        ",".join(k+":"+cell(approvals[k],2) for k in release_keys),
        cell(approvals[release_keys[-1]],7),
        "Even PASS never authorizes automatic production promotion")
    report=approvals.get("Three subscription Reports")
    if report is None:raise ValueError("SFDC_REPORT_ACCEPTANCE_MISSING")
    status=cell(report,2)
    age=(now-timestamp(cell(report,7))).total_seconds()/3600 if timestamp(cell(report,7)) else None
    add("SFDC","3-report source acceptance snapshot",
        "PASS" if status=="PASS" and age is not None and 0<=age<=8 else "REVIEW",
        "CSS Operational Acceptance","Original report due slots current and acceptance snapshot <=8h",
        "state="+status+";acceptance_age_h="+
          (str(round(age,1)) if age is not None else "UNKNOWN"),cell(report,7),
        "Workflow execution success does not prove new subscription attachments arrived")

    mail=data["mail"]
    m=mail[1] if len(mail)>1 else None
    ok=bool(m and cell(m,1)=="WINDOW_CAUGHT_UP" and n(cell(m,7))==0 and n(cell(m,11))==0)
    add("Mail","60-day body cache completion",
        "PASS" if ok else "REVIEW","CSS Mail Backfill Status",
        "WINDOW_CAUGHT_UP; remaining=0; errors=0",
        "state="+cell(m,1)+";remaining="+cell(m,7)+";errors="+cell(m,11),
        cell(m,0),
        "Scope is personal inbox/sent and eligible 60-day window, not entire mailbox")
    return output

def summary(rows):
    return {"checks":len(rows),"states":dict(collections.Counter(r[2] for r in rows)),
            "source_caveats_preserved":True,"revenue_or_customer_writes":0}

def request_with_retry(session,method,url,**kwargs):
    """Retry idempotent Sheets GET/PUT only; never retry an ambiguous POST write."""
    action=method.upper()
    if action not in ("GET","PUT","POST"):
        raise ValueError("UNSUPPORTED_SHEETS_METHOD")
    delays=(0,1,2,4)
    for index,delay in enumerate(delays):
        if delay:time.sleep(delay)
        resp=session.request(action,url,timeout=55,**kwargs)
        if resp.status_code in (429,500,502,503,504) and action in ("GET","PUT") and index<len(delays)-1:
            continue
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    raise RuntimeError("SHEETS_HTTP_RETRIES_EXHAUSTED")

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("CKD_DRIVE_SA_JSON","")
    run=os.getenv("GITHUB_RUN_ID","")
    if not raw:raise RuntimeError("NO_GOOGLE_SERVICE_ACCOUNT")
    if not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_GITHUB_RUN")
    session=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def send(method,url,**kwargs):
        return request_with_retry(session,method,url,**kwargs)
    batch=send("GET",root+"/values:batchGet",
        params=[("ranges",v[0]) for v in SOURCES.values()])
    got=batch.get("valueRanges",[])
    if len(got)!=len(SOURCES):raise RuntimeError("INCOMPLETE_SOURCE_SNAPSHOT")
    data={k:z.get("values",[]) for k,z in zip(SOURCES,got)}
    rows=analyze(data,dt.datetime.now(KST))
    if len(rows)!=10:raise RuntimeError("EVIDENCE_CHECK_COVERAGE_DRIFT")
    link="https://github.com/kimtk94/Codex/actions/runs/"+run
    stamped=[row[:-1]+[link] for row in rows]
    wanted=[HEAD]+stamped
    metadata=send("GET",root,params={"fields":"sheets.properties(title,sheetId)"})
    existing=[s for s in metadata.get("sheets",[])
              if s.get("properties",{}).get("title")==TAB]
    if not existing:
        send("POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":100,"columnCount":10,"frozenRowCount":1}}}}]})
    a1=root+"/values/"+quote("'"+TAB+"'!A1:J"+str(len(wanted)),safe="")
    old=send("GET",a1).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("EXCEPTION_SHEET_FOREIGN_HEADER")
    send("PUT",a1,params={"valueInputOption":"RAW"},json={"values":wanted})
    readback=send("GET",a1).get("values",[])
    if readback!=[[str(x) for x in r] for r in wanted]:
        raise RuntimeError("EXCEPTION_SHEET_READBACK_FAILED")
    print("CSS_EVIDENCE_EXCEPTIONS="+json.dumps(summary(rows),sort_keys=True))
    print("BUSINESS_GATES_NOT_AUTO_PROMOTED;GENERATED_REVIEW_ONLY;NO_REVENUE_ADDITION")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        code=getattr(getattr(exc,"response",None),"status_code",None)
        detail="_HTTP_"+str(code) if isinstance(code,int) else ""
        print("CSS_EVIDENCE_EXCEPTION_FAILED="+type(exc).__name__+detail,file=sys.stderr)
        sys.exit(1)
