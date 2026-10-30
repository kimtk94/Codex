#!/usr/bin/env python3
"""Centralize selected GitHub Actions outcomes in one dedicated Sheets status tab.

Strictly a status ledger: no user mail, sales CRM mutation or source-sheet edits.
A successful workflow run is NOT formal task acceptance.
"""
import base64
import datetime as dt
import json
import os
import sys
from urllib.parse import quote
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

REPO="kimtk94/Codex"
BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="Automation Workflow Runs"
UTC=dt.timezone.utc
KST=dt.timezone(dt.timedelta(hours=9))
HEADERS=["Workflow","Domain","Run State","Last Run UTC","Age Hours",
         "GitHub Run URL","Event","Checked KST","Verification Boundary","Workflow File"]
# A status row never claims user-facing email was sent or SFDC values saved.
WORKFLOWS=(
 ("QQ Mail Source","Mail","css-mail-readonly.yml",6,"Read-only IMAP/source probe"),
 ("SFDC 3-Report Ingest","Report","sfdc-three-report-email-digestion.yml",8,"3-report staging; not Salesforce writeback"),
 ("Lead Personal Audit","Lead","lead-unsent-gap-refresh.yml",8,"Exact personal sender evidence; no emails sent"),
 ("NBA Pipeline","Follow-up","nba-verified-pool-pipeline.yml",8,"Pool validation and approved scheduled staging"),
 ("Email Decision Sync","Mail","sfdc-email-decisions-sync.yml",4,"QQ/SFDC review-ledger parity; no user sends"),
 ("BI Mail Review Sync","Mail","bi-mail-review-sync.yml",4,"QQ mail exclusion decision audit; test and apply tracked separately"),
 ("Revenue / Parallel QA","Revenue","parallel-sales-verification.yml",12,"Read-only 4-track verification; not bank receipt"),
 ("Feishu Schema Audit","Payment","feishu-latest-four-schema.yml",4,"Raw table schema QA; failures block payment certification"),
 ("Feishu Project Sync","Projects","feishu-project-sync.yml",24,"Feishu source projection only"),
 ("Web Body Sync","Web","css-web-body-sync.yml",24,"Source-body caching/availability, not browser E2E"),
 ("Web Console CI","Web","css-central-operations-console-tests.yml",72,"Mock/static tests only; authenticated E2E pending"),
)


def parse_time(raw):
    if not raw:raise ValueError("EMPTY_RUN_TIMESTAMP")
    return dt.datetime.fromisoformat(raw.replace("Z","+00:00")).astimezone(UTC)


def evaluate_runs(runs, now, threshold_hours):
    valid=[r for r in runs if r.get("head_branch")=="main"]
    valid.sort(key=lambda r:r.get("created_at") or "",reverse=True)
    if not valid:
        return "NOT_RUN","",None,"",None
    top=valid[0]
    if top.get("status")!="completed":
        return "IN_PROGRESS",top.get("updated_at") or top.get("created_at") or "",None,top.get("event") or "",top
    t=parse_time(top.get("updated_at") or top.get("created_at"))
    age=round((now-t).total_seconds()/3600,1)
    conclusion=top.get("conclusion")
    status={"success":"PASS_EXECUTION_ONLY","failure":"FAILED","cancelled":"CANCELLED",
            "timed_out":"FAILED","action_required":"BLOCKED",
            "skipped":"SKIPPED"}.get(conclusion,"UNVERIFIED")
    if age>threshold_hours and status=="PASS_EXECUTION_ONLY":
        status="STALE"
    return status,t.strftime("%Y-%m-%dT%H:%M:%SZ"),age,top.get("event") or "",top


def make_rows(fetch, now):
    rows=[]
    seen=set()
    for label,group,filename,threshold,boundary in WORKFLOWS:
        if filename in seen:raise ValueError("DUPLICATE_WORKFLOW_FILENAME")
        seen.add(filename)
        runs=fetch(filename)
        state,time,age,event,run=evaluate_runs(runs,now,threshold)
        url=""
        if run:
            rid=run.get("id")
            if not isinstance(rid,int) or rid<=0:raise ValueError("INVALID_ACTIONS_RUN_ID")
            url="https://github.com/"+REPO+"/actions/runs/"+str(rid)
        rows.append([label,group,state,time,str(age) if age is not None else "",
                     url,event,now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
                     boundary,filename])
    return [HEADERS]+rows


def github_fetch(filename):
    gh=os.environ.get("GITHUB_TOKEN")
    if not gh:raise RuntimeError("GITHUB_READ_TOKEN_MISSING")
    url="https://api.github.com/repos/"+REPO+"/actions/workflows/"+quote(filename)+"/runs"
    response=requests.get(url,headers={"Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+gh,"X-GitHub-Api-Version":"2022-11-28"},
        params={"branch":"main","per_page":12},timeout=35)
    response.raise_for_status()
    data=response.json()
    rows=data.get("workflow_runs")
    if not isinstance(rows,list):raise RuntimeError("GITHUB_WORKFLOW_RUNS_MISSING")
    return rows


def google_client():
    raw=os.environ.get("CKD_DRIVE_SA_JSON")
    if not raw:raise RuntimeError("SHEET_WRITER_CREDENTIAL_MISSING")
    try:
        info=json.loads(raw)
    except (ValueError,TypeError):
        info=json.loads(base64.b64decode(raw))
    creds=service_account.Credentials.from_service_account_info(
        info,scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)


def publish(session, rows):
    base="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    metadata=session.get(base,params={"fields":"sheets.properties(title,sheetId,gridProperties)"},timeout=35)
    metadata.raise_for_status()
    options=[x["properties"] for x in metadata.json().get("sheets",[])
             if x.get("properties",{}).get("title")==TAB]
    if options:
        props=options[0]
        if props.get("gridProperties",{}).get("columnCount",0)<len(HEADERS):
            raise ValueError("WORKFLOW_HEALTH_COLUMN_CAPACITY_INVALID")
    else:
        create=session.post(base+":batchUpdate",json={"requests":[{"addSheet":{
            "properties":{"title":TAB,"gridProperties":{"rowCount":100,
                "columnCount":len(HEADERS),"frozenRowCount":1}}}}]},timeout=35)
        create.raise_for_status()
    location=base+"/values/"+quote("'"+TAB+"'!A1:J"+str(len(rows)),safe="")
    up=session.put(location,params={"valueInputOption":"RAW"},
        json={"values":rows},timeout=45)
    up.raise_for_status()
    check=session.get(location,timeout=45)
    check.raise_for_status()
    if check.json().get("values")!=rows:
        raise RuntimeError("CENTRAL_RUN_STATUS_READBACK_MISMATCH")
    return sum(r[2]=="FAILED" for r in rows[1:])


def main():
    now=dt.datetime.now(UTC)
    rows=make_rows(github_fetch,now)
    if len(rows)!=len(WORKFLOWS)+1:
        raise RuntimeError("WORKFLOW_COVERAGE_INVALID")
    failures=publish(google_client(),rows)
    print("CENTRAL_WORKFLOW_STATUS=WRITTEN READBACK_VERIFIED=true "+
          "TRACKED="+str(len(WORKFLOWS))+" FAILURES="+str(failures))
    # Recording a failed upstream workflow is an expected, valuable audit
    # outcome; it must not be mislabeled as failure of the publisher itself.


if __name__=="__main__":
    try:main()
    except Exception as e:
        print("CENTRAL_WORKFLOW_PUBLISH_FAILED="+type(e).__name__,file=sys.stderr)
        sys.exit(1)
