#!/usr/bin/env python3
"""Independent, read-only verification of Friday-Thursday Quote KPI counts.

Never turn an empty historical weekly source field into zero approvals. A
0 observed in a *partial* approval-mail ledger is not complete mail coverage.
This gate can assert that populated weekly counts match the immutable
Salesforce IDs; absent counts remain explicit coverage gaps.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SHEET = os.getenv("SFDC_UNIFIED_SHEET_ID",
                  "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
WEEKLY = "SFDC Weekly Overview"
APPROVALS = "Quote Approval Dedup"
HEAD_WEEK = ["week_start","week_end","weekly_basis","opportunity_created",
             "opportunity_closed_target","opportunity_closed_won_target",
             "quotation_approvals","approvals_created_in_week"]
HEAD_APPROVAL = ["Approval KST","AMEA Quotation ID","Quotation Name",
                 "SFDC Record ID","Approval Evidence","Week Status"]
WEEK_STATUS = re.compile(r"^(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})$")
COUNT = re.compile(r"^\d+$")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT = PROJECT_ROOT / "quote_weekly_coverage.json"

def read_values(session,tab,span):
    address=urllib.parse.quote("'"+tab.replace("'","''")+"'!"+span,safe="")
    url="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET+"/values/"+address
    response=session.get(url,timeout=45)
    if not response.ok:
        raise RuntimeError("SOURCE_READ_HTTP_"+str(response.status_code))
    return response.json().get("values",[])

def date_or_fail(value):
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise RuntimeError("WEEK_DATE_INVALID") from None

def audit(weekly_rows, approval_rows):
    if not weekly_rows or weekly_rows[0][:8]!=HEAD_WEEK:
        raise RuntimeError("WEEKLY_SOURCE_HEADER_CHANGED")
    if not approval_rows or approval_rows[0][:6]!=HEAD_APPROVAL:
        raise RuntimeError("APPROVAL_SOURCE_HEADER_CHANGED")
    by_week=defaultdict(set)
    for row in approval_rows[1:]:
        if len(row)<6:
            raise RuntimeError("APPROVAL_SOURCE_MISSING_COLUMNS")
        status=str(row[5] or "").strip()
        match=WEEK_STATUS.fullmatch(status)
        if not match:
            raise RuntimeError("APPROVAL_WEEK_RANGE_INVALID")
        start,end=map(date_or_fail,match.groups())
        if start.weekday()!=4 or end-start!=dt.timedelta(days=6):
            raise RuntimeError("APPROVAL_WEEK_RANGE_NOT_FRIDAY_THURSDAY")
        identifier=str(row[3] or "").strip()
        if not identifier:
            raise RuntimeError("APPROVAL_IMMUTABLE_ID_MISSING")
        by_week[start.isoformat()].add(identifier)

    out=[]
    seen=set()
    for row in weekly_rows[1:]:
        if not row or not row[0]:
            continue
        if len(row)<7:
            raise RuntimeError("WEEKLY_SOURCE_ROW_TOO_SHORT")
        start,end=date_or_fail(row[0]),date_or_fail(row[1])
        key=start.isoformat()
        if key in seen:
            raise RuntimeError("DUPLICATE_WEEKLY_SOURCE_WEEK")
        seen.add(key)
        if start.weekday()!=4 or end-start!=dt.timedelta(days=6):
            raise RuntimeError("WEEK_NOT_FRIDAY_TO_THURSDAY")
        observed=len(by_week.get(key,set()))
        raw=str(row[6] if len(row)>6 and row[6] is not None else "").strip()
        if not raw:
            if observed:
                status="MISSING_COUNT_WITH_APPROVAL_EVIDENCE"
            else:
                status="UNVERIFIED_SOURCE_GAP"
            source_count=None
        elif not COUNT.fullmatch(raw):
            raise RuntimeError("NONINTEGER_WEEKLY_QUOTE_COUNT")
        else:
            source_count=int(raw)
            status=("VERIFIED_SOURCE_PARITY" if source_count==observed
                    else "WEEKLY_COUNT_SOURCE_CONFLICT")
        out.append({"week_start":key,"week_end":end.isoformat(),
                    "source_approved_count":source_count,
                    "observed_immutable_approval_ids":observed,
                    "status":status})
    if not out:
        raise RuntimeError("EMPTY_WEEKLY_SOURCE")
    absent=set(by_week)-seen
    if absent:
        raise RuntimeError("APPROVAL_WEEKS_ABSENT_FROM_SOURCE")
    out.sort(key=lambda d:d["week_start"],reverse=True)
    counts={status:sum(x["status"]==status for x in out) for status in (
        "VERIFIED_SOURCE_PARITY","UNVERIFIED_SOURCE_GAP",
        "MISSING_COUNT_WITH_APPROVAL_EVIDENCE","WEEKLY_COUNT_SOURCE_CONFLICT")}
    report={"weekly_source_rows":len(out),
            "verified_weeks":counts["VERIFIED_SOURCE_PARITY"],
            "coverage_gaps":counts["UNVERIFIED_SOURCE_GAP"],
            "source_conflicts":counts["MISSING_COUNT_WITH_APPROVAL_EVIDENCE"]+
                               counts["WEEKLY_COUNT_SOURCE_CONFLICT"],
            "source_approved_sum":sum(x["source_approved_count"] or 0 for x in out),
            "immutable_approval_sum":sum(x["observed_immutable_approval_ids"] for x in out),
            "gap_weeks":[x["week_start"] for x in out if x["status"]=="UNVERIFIED_SOURCE_GAP"],
            "weeks":out,"zero_is_not_imputed":True}
    return report

def main():
    creds=service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    result=audit(read_values(session,WEEKLY,"A1:H1500"),
                 read_values(session,APPROVALS,"A1:F1600"))
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary=("QUOTE_WEEKLY_PARITY_AUDIT weeks=%d verified=%d gaps=%d "
             "conflicts=%d source_sum=%d evidence_sum=%d no_zero_imputation=true" %
             (result["weekly_source_rows"],result["verified_weeks"],
              result["coverage_gaps"],result["source_conflicts"],
              result["source_approved_sum"],result["immutable_approval_sum"]))
    print(summary,flush=True)
    markdown=os.getenv("GITHUB_STEP_SUMMARY")
    if markdown:
        with open(markdown,"a",encoding="utf-8") as f:
            f.write("### Quote weekly source parity\n\n"+summary+"\n\n")
            f.write("Historical null counts remain NULL, never zero. Missing weeks:\n")
            for x in result["gap_weeks"]:
                f.write("- "+x+"\n")
    if result["source_conflicts"]:
        raise RuntimeError("WEEKLY_SOURCE_APPROVAL_PARITY_FAILED")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("QUOTE_WEEKLY_PARITY_GATE_FAILED "+type(e).__name__,file=sys.stderr)
        raise
