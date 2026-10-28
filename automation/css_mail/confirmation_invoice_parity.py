#!/usr/bin/env python3
"""Read-only reconciliation of Statement-Ready notice gaps with issued invoice evidence."""
import json,os,urllib.parse
from collections import defaultdict,Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from confirmation_contract_gaps import scan,BOOK

SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
def table(s,book,name,area):
    path=urllib.parse.quote("'"+name+"'!"+area,safe="")
    r=s.get("https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+path,timeout=90)
    r.raise_for_status()
    return r.json().get("values",[])
def dicts(rows):
    if not rows:return []
    return [dict(zip(rows[0],r)) for r in rows[1:] if r]
def main():
    creds=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s=AuthorizedSession(creds)
    raw=table(s,BOOK,"Canonical Mail Ledger","A1:AA60000")
    if not raw or len(raw[0])<27 or raw[0][14]!="subject":raise RuntimeError("CANONICAL_SCHEMA_CHANGED")
    gaps=scan(raw[1:])
    invoice_rows=dicts(table(s,SFDC,"CSS Tax Invoices","A1:N15000"))
    index=defaultdict(list)
    for row in invoice_rows:
        project=row.get("project_id","").strip().upper()
        contract=row.get("h_project_number","").strip().upper()
        no=row.get("invoice_number","").strip()
        if project and contract and no:index[(project,contract)].append(row)
    report=[]
    for gap in gaps:
        invoices=index.get((gap["amea"],gap["contract"]),[])
        numbers=sorted({r.get("invoice_number","") for r in invoices})
        if invoices:
            state="ISSUED_INVOICE_EXISTS_CONTRACT_LEVEL_BATCH_UNVERIFIED"
        elif gap["contract"]=="H_UNSPECIFIED":
            state="REVIEW_CONTRACT_UNRESOLVED"
        else:
            state="NO_ISSUED_INVOICE_IN_CSS_LEDGER_REVIEW"
        report.append({"amea":gap["amea"],"contract":gap["contract"],
            "sam":gap["sam"],"invoice_numbers":numbers,"status":state})
    counts=Counter(x["status"] for x in report)
    print("CONFIRMATION_INVOICE_PARITY "+json.dumps({
        "contract_gap_records":len(report),"source_invoice_rows":len(invoice_rows),
        "by_status":dict(counts),"items":report,
        "confirmed_unissued":0,"owner_verified":0,
        "note":"Contract-level invoice presence does not prove each SAM batch was invoiced."
    },ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
