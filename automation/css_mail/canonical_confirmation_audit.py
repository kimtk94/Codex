#!/usr/bin/env python3
"""Read-only confirmation evidence audit. Never infer customer approval from a notice."""
import json,os,re,sys,urllib.parse
from collections import defaultdict,Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
PAT=re.compile(r"AMEA\d{7,}(?:-\d{1,3})?",re.I)
NOTICE=re.compile(r"Final Report\s*&\s*Statement Ready For Confirmation",re.I)
ISSUED=re.compile(r"Invoice Issued\s*&\s*Statement Confirmed",re.I)
def classify(subject):
    if ISSUED.search(subject):return "INVOICE_ISSUED_NOTICE"
    if NOTICE.search(subject):return "STATEMENT_READY_NOTICE"
    return None
def run():
    creds=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s=AuthorizedSession(creds)
    a=urllib.parse.quote("'Canonical Mail Ledger'!A1:AA60000",safe="")
    r=s.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+a,timeout=90)
    r.raise_for_status()
    rows=r.json().get("values",[])
    if not rows or rows[0][0]!="canonical_key" or len(rows[0])<27 or rows[0][14]!="subject":
        raise RuntimeError("CANONICAL_SCHEMA_CHANGED")
    by_key=defaultdict(set)
    for row in rows[1:]:
        def v(i):return str(row[i]).strip() if len(row)>i else ""
        state=classify(v(14))
        if not state:continue
        projects=set(PAT.findall(" ".join([v(14),v(17)])))
        for project in projects:by_key[project.upper()].add(state)
    counts=Counter()
    for states in by_key.values():
        for state in states:counts[state]+=1
        if "STATEMENT_READY_NOTICE" in states and "INVOICE_ISSUED_NOTICE" not in states:
            counts["READY_WITHOUT_ISSUED_NOTICE"]+=1
    print("CANONICAL_CONFIRMATION_EVIDENCE "+json.dumps({
        "projects_with_statement_ready_notice":counts["STATEMENT_READY_NOTICE"],
        "projects_with_issued_notice":counts["INVOICE_ISSUED_NOTICE"],
        "projects_ready_without_issued_notice":counts["READY_WITHOUT_ISSUED_NOTICE"],
        "customer_confirmation_verified":0,
        "sfdc_owner_verified":0,
        "revenue_confirmed_by_this_audit":False,
        "note":"Notice subjects are NOT proof of customer confirmation or owner."
    },sort_keys=True))
if __name__=="__main__":
    try:run()
    except Exception as e:
        print("CANONICAL_CONFIRMATION_AUDIT_FAILED "+type(e).__name__+":"+str(e)[:160],file=sys.stderr);sys.exit(1)
