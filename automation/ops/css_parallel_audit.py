#!/usr/bin/env python3
"""Independent, read-only gate checks for parallel CSS automation jobs.

No PII, sheet writes, Salesforce mutations or email sends. Emits compact
machine-verifiable evidence for GitHub Actions and requires the latest source
schemas to match. Fail closed on absent/invalid source records.
"""
import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SHEET = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
KST = dt.timezone(dt.timedelta(hours=9))
STATUSES = {"SENT_AFTER_LEAD_CONFIRMED", "SENT_BEFORE_LEAD_ONLY",
            "NO_PERSONAL_OUTBOUND_EVIDENCE"}


def dateparse(text):
    value = str(text or "").removesuffix(" KST").strip()
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Date format invalid") from exc
    return result if result.tzinfo else result.replace(tzinfo=KST)


def currency(value):
    try:
        return int(str(value or "0").replace("₩", "").replace(",", "").strip())
    except ValueError as exc:
        raise ValueError("Invalid currency amount") from exc


def rowvalue(row, offset):
    return str(row[offset]).strip() if len(row) > offset and row[offset] is not None else ""


def assert_fresh(value, now, max_hours=72):
    age = now.astimezone(KST)-dateparse(value).astimezone(KST)
    if age < -dt.timedelta(hours=2) or age > dt.timedelta(hours=max_hours):
        raise ValueError("Stale or future-dated source timestamp")


def audit_lead(report, raw_leads, personal, pool, analytics, now):
    if not report or rowvalue(report[0],0)!="Entity":
        raise ValueError("SFDC 3-report ingest audit absent")
    if not raw_leads or "SFDC Lead ID" not in raw_leads[0]:
        raise ValueError("SFDC Lead Report schema missing")
    if not personal or rowvalue(personal[0],0)!="Lead ID" or rowvalue(personal[0],14)!="My Mail Status":
        raise ValueError("Personal Lead audit schema missing")
    if not pool or rowvalue(pool[0],3)!="Source" or rowvalue(pool[0],4)!="Record ID":
        raise ValueError("NBA Pool schema missing")
    ix = raw_leads[0].index("SFDC Lead ID")
    leads = {rowvalue(r,ix) for r in raw_leads[1:] if rowvalue(r,ix)}
    audit = [r for r in personal[1:] if rowvalue(r,0)]
    ids = [rowvalue(r,0) for r in audit]
    if len(ids)!=len(set(ids)) or set(ids)!=leads or len(ids)<450:
        raise ValueError("Personal audit Lead IDs differ from current SFDC Report")
    source = {rowvalue(r,0):r for r in report[1:] if rowvalue(r,0) in ("Leads","Opportunities","Quotation")}
    if set(source)!=set(("Leads","Opportunities","Quotation")):
        raise ValueError("Missing one of three SFDC subscription reports")
    for name in source:
        r=source[name]
        if rowvalue(r,8)!="STAGED_NOT_PROMOTED" or currency(rowvalue(r,6))!=0:
            raise ValueError("SFDC Report staging evidence invalid")
        assert_fresh(rowvalue(r,1),now)
    if currency(rowvalue(source["Leads"],3))!=len(ids):
        raise ValueError("Lead ingest record-count mismatch")
    qq_times={rowvalue(r,18) for r in audit}
    if len(qq_times)!=1:
        raise ValueError("Inconsistent QQ personal sent audit snapshots")
    assert_fresh(next(iter(qq_times)),now)
    counts={state:0 for state in STATUSES}
    for r in audit:
        state=rowvalue(r,14)
        if state not in counts:
            raise ValueError("Unknown personal sent evidence state")
        counts[state]+=1
    excluded={rowvalue(r,0) for r in audit if rowvalue(r,7).upper() in
              ("QUALIFIED","CONVERTED","CLOSED","UNQUALIFIED") or rowvalue(r,8)}
    pool_leads=[r for r in pool[1:] if rowvalue(r,3)=="LEAD" and rowvalue(r,4)]
    key=[rowvalue(r,4) for r in pool_leads]
    if len(set(key))!=len(key):
        raise ValueError("Duplicate Lead in NBA Pool")
    evidence={rowvalue(r,0):rowvalue(r,14) for r in audit}
    if any(evidence.get(rowvalue(r,4))!=rowvalue(r,11)
           or rowvalue(r,4) in excluded for r in pool_leads):
        raise ValueError("Personal Lead evidence mismatch leaked into NBA Pool")
    if any(evidence.get(x)=="SENT_AFTER_LEAD_CONFIRMED" for x in key):
        raise ValueError("Already contacted Lead requeued")
    warnings=[]
    if analytics and any(rowvalue(r,0)=="Lead records" and
                         rowvalue(r,1)!=str(len(ids)) for r in analytics[1:]):
        warnings.append("Legacy 3Report Analytics is not updated to latest Lead staging")
    return {
        "track":"report_lead","result":"PASS_WITH_REVIEW" if warnings else "PASS",
        "leads":len(ids),"opportunities":currency(rowvalue(source["Opportunities"],4)),
        "quotes_unique":currency(rowvalue(source["Quotation"],4)),
        "sent_after":counts["SENT_AFTER_LEAD_CONFIRMED"],
        "prior_only":counts["SENT_BEFORE_LEAD_ONLY"],
        "no_personal_outbound":counts["NO_PERSONAL_OUTBOUND_EVIDENCE"],
        "nba_leads":len(pool_leads),
        "warnings":warnings,
        "qq_snapshot":next(iter(qq_times)),
    }


def audit_revenue(monthly,ledger,fx_sheet,now):
    if not monthly or rowvalue(monthly[0],0)!="Month" or len(monthly[0])<17:
        raise ValueError("Revenue Monthly schema invalid")
    if not ledger or rowvalue(ledger[0],14)!="Statement ID":
        raise ValueError("Batch Statement Ledger schema invalid")
    if not fx_sheet or rowvalue(fx_sheet[1],0)!="Reporting FX KRW per USD":
        raise ValueError("Reporting FX setting missing")
    fx=float(rowvalue(fx_sheet[1],1))
    if fx<=0:
        raise ValueError("Nonpositive reporting FX")
    current=now.astimezone(KST).strftime("%Y-%m")
    target=next((r for r in monthly[1:] if rowvalue(r,0)==current),None)
    if not target:
        raise ValueError("No current-month Revenue snapshot")
    actual,pending,forecast=[currency(rowvalue(target,i)) for i in (1,2,3)]
    verified=currency(rowvalue(target,12))
    if verified!=actual+pending or min(actual,pending,forecast)<0:
        raise ValueError("Revenue Actual+Pending parity invalid")
    if abs(float(rowvalue(target,15))-(verified/fx/1000))>0.002:
        raise ValueError("Reporting FX kUSD parity invalid")
    assert_fresh(rowvalue(target,11),now)
    seen=set()
    pending_source=0
    pending_count=0
    watches=[]
    for r in ledger[1:]:
        if rowvalue(r,11)!="PENDING_VERIFIED_NOT_ACTUAL":
            continue
        stmt=rowvalue(r,14)
        if not stmt or stmt in seen:
            raise ValueError("Missing/duplicate pending Statement installment ID")
        seen.add(stmt)
        if rowvalue(r,7):
            raise ValueError("Pending Statement already has Invoice ID")
        pending_source+=currency(rowvalue(r,5))
        pending_count+=1
        watches.append(rowvalue(r,16))
    if pending_source!=pending or pending_count!=currency(rowvalue(target,6)):
        raise ValueError("Pending original Statement amounts/count do not reconcile")
    warnings=[]
    overdue=sum(x=="AUTO_ISSUE_OVERDUE_REVIEW" for x in watches)
    if overdue:
        warnings.append("Original invoice evidence still required for overdue Statements")
    partial=currency(rowvalue(target,9))
    if partial:
        warnings.append("Partial invoice allocation reviews not finalized")
    return {
        "track":"revenue","result":"PASS_WITH_REVIEW" if warnings else "PASS",
        "month":current,"invoice_actual_krw":actual,"verified_pending_krw":pending,
        "verified_billing_krw":verified,"forecast_separate_krw":forecast,
        "pending_installments":pending_count,"overdue_review":overdue,
        "partial_allocation_reviews":partial,"reporting_fx_krw_usd":fx,
        "warnings":warnings
    }


def read_google(ranges):
    secret=os.environ.get("CKD_DRIVE_SA_JSON")
    if not secret:
        raise ValueError("Missing CKD_DRIVE_SA_JSON (not a success)")
    config=json.loads(secret)
    creds=service_account.Credentials.from_service_account_info(config,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    reply=session.get(
        "https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+"/values:batchGet",
        params=[("ranges",r) for r in ranges]+[("valueRenderOption","FORMATTED_VALUE")],
        timeout=45)
    reply.raise_for_status()
    found=reply.json().get("valueRanges",[])
    if len(found)!=len(ranges):
        raise ValueError("Google Sheet range response incomplete")
    return [part.get("values",[]) for part in found]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("track",choices=("lead","revenue"))
    args=parser.parse_args()
    now=dt.datetime.now(KST)
    if args.track=="lead":
        v=read_google(["'SFDC Email Ingest Audit'!A1:J12",
                       "'SFDC Email Leads Raw'!A1:W700",
                       "'Lead My Sent Audit'!A1:T650",
                       "'NBA Action Pool'!A1:N2000",
                       "'SFDC 3Report Analytics'!A1:B15"])
        result=audit_lead(*v,now)
    else:
        v=read_google(["'BI Revenue Lifecycle Monthly'!A1:Q24",
                       "'CSS Batch Statement Ledger'!A1:T250",
                       "'Revenue FX Settings'!A1:C5"])
        result=audit_revenue(*v,now)
    output=Path("audit-results")
    output.mkdir(exist_ok=True)
    (output/(args.track+".json")).write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PARALLEL_AUDIT_RESULT="+json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
