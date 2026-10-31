#!/usr/bin/env python3
"""Publish the ten independent parallel CI outcome rows to an isolated generated status tab.

Never overwrite customer decisions, source invoices, mail content, or billing.
Execution result is NOT equivalent to business acceptance.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "CSS P0 Parallel Status"
HEADER = ["Track", "Execution", "Check Scope", "Acceptance", "GitHub Run", "Checked KST", "Boundary"]
TRACKS = (
    ("QQ source checkpoint", "TRACK_MAIL", "Read-only key/fetch freshness", "No source or mail changes"),
    ("Revenue and VAT", "TRACK_REVENUE", "Invoice/Statement/forecast cross-source", "Payment and owner receipt not assumed"),
    ("Invoice cross-source gaps", "TRACK_INVOICE_REVIEW", "QQ original vs canonical / extract; generated review only", "Owner not verified; no auto revenue booking"),
    ("Invoice owner / receipt candidates", "TRACK_OWNER_PAYMENT", "Exact CMS, H/X project, gross and receipt candidates", "Sales tag is not ownership; receipt candidate is not paid"),
    ("Lead personal parity", "TRACK_LEAD", "Exact-personal sender and NBA exclusion", "No user email or SFDC Save"),
    ("Feishu payment schema", "TRACK_FEISHU", "Raw four-sheet headers + Google mirror parity", "Structure does not certify bank receipt"),
    ("Web API source contract", "TRACK_WEB", "Source-backed local API auth/UID and current net", "No owner-authenticated Vercel E2E"),
    ("Source evidence exceptions", "TRACK_EVIDENCE", "Invoice coverage, payment source age, release gates", "Successful audit can still contain REVIEW/BLOCK business evidence"),
    ("AMEA contract lineage quarantine", "TRACK_CONTRACT", "Exact AMEA/X review and positional Watch warning", "Candidates not certified contracts, issued invoices, or paid revenue"),
    ("Vercel release evidence", "TRACK_RELEASE", "Read-only production SHA/project root when token exists", "No deploy, production acceptance or rollback"),
)
ALLOWED = {"success", "failure", "cancelled", "skipped"}
def rows_from_environment(env, stamp):
    statuses=[env.get(key, "") for _,key,_,_ in TRACKS]
    if any(v not in ALLOWED for v in statuses):
        raise ValueError("UNKNOWN_PARALLEL_TRACK_STATE")
    run=env.get("GITHUB_RUN_ID", "")
    if not run.isdigit() or env.get("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise ValueError("INVALID_GITHUB_RUN_CONTEXT")
    link="https://github.com/kimtk94/Codex/actions/runs/"+run
    return [[label, result.upper()+"_EXECUTION_ONLY", scope, "NOT_VERIFIED", link, stamp, boundary]
            for (label, _, scope, boundary),result in zip(TRACKS,statuses)]

def main():
    raw=os.environ.get("CKD_DRIVE_SA_JSON","")
    if not raw:
        raise RuntimeError("MISSING_SHEETS_CREDENTIAL")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    client=AuthorizedSession(service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    base="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def req(method,uri,body=None):
        response=client.request(method,base+uri,json=body,timeout=40)
        response.raise_for_status()
        return response.json() if response.content else {}
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST")
    out=rows_from_environment(os.environ,now)
    sheets=req("GET","?fields=sheets.properties(title,sheetId)")
    matches=[x for x in sheets.get("sheets",[]) if x.get("properties",{}).get("title")==TAB]
    if not matches:
        req("POST",":batchUpdate",{"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"rowCount":200,"columnCount":7,"frozenRowCount":1}}}}]})
    target="/values/"+urllib.parse.quote("'"+TAB+"'!A1:G"+str(len(out)+1),safe="")
    previous=req("GET",target).get("values",[])
    if previous and previous[0]!=HEADER:
        raise RuntimeError("P0_PARALLEL_FOREIGN_TAB_HEADER")
    # No clear, no append, no other target sheet edits.
    req("PUT",target+"?valueInputOption=RAW",{"values":[HEADER]+out})
    observed=req("GET",target).get("values",[])
    if observed!=[HEADER]+out:
        raise RuntimeError("P0_PARALLEL_RESULT_READBACK_MISMATCH")
    print("CSS_P0_PARALLEL_STATUS_WRITTEN tracks="+str(len(out))+" readback_verified=true "
          "success="+str(sum(r[1]=="SUCCESS_EXECUTION_ONLY" for r in out)))
    print("CSS_P0_ACCEPTANCE_NOT_PROMOTED")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_P0_PARALLEL_PUBLISH_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
