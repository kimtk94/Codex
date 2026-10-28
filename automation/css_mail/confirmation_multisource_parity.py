#!/usr/bin/env python3
"""Read-only cross-ledger invoice evidence for Statement Ready notice gaps."""
import json,os,urllib.parse
from collections import defaultdict,Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from confirmation_contract_gaps import scan,BOOK

SFDC="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
SOURCES=[
 (BOOK,"CSS Tax Invoice List","A1:N12000","project_id","h_project_number","invoice_number"),
 (BOOK,"QQ 2026 Invoice Backfill","A1:K12000","amea_project_id","h_project_id","invoice_number"),
 (SFDC,"Revenue Invoice Base","A1:M12000","AMEA ID","H Project ID","Invoice No"),
 (SFDC,"CSS Tax Invoices","A1:N12000","project_id","h_project_number","invoice_number"),
]
def read(session,book,tab,area):
    q=urllib.parse.quote("'"+tab+"'!"+area,safe="")
    response=session.get("https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+q,timeout=90)
    response.raise_for_status()
    return response.json().get("values",[])
def rows(values):
    return [dict(zip(values[0],r)) for r in values[1:] if r] if values else []
def compare(gaps,evidence):
    exact=defaultdict(lambda:defaultdict(set))
    for name,items,pk,hk,nk in evidence:
        for item in items:
            project=str(item.get(pk,"")).strip().upper()
            contract=str(item.get(hk,"")).strip().upper()
            invoice=str(item.get(nk,"")).strip()
            if project and contract and invoice:
                exact[(project,contract)][invoice].add(name)
    result=[]
    for gap in gaps:
        found=exact.get((gap["amea"],gap["contract"]),{})
        result.append({"amea":gap["amea"],"h_contract":gap["contract"],
            "sam_batches":gap["sam"],"invoice_numbers":sorted(found),
            "evidence_sources":sorted({source for sources in found.values() for source in sources}),
            "status":"INVOICE_FOUND_BATCH_NOT_VERIFIED" if found else "NO_EXACT_INVOICE_EVIDENCE_REVIEW"})
    return result
def main():
    creds=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    mail=read(session,BOOK,"Canonical Mail Ledger","A1:AA60000")
    if not mail or len(mail[0])<27 or mail[0][14]!="subject":raise RuntimeError("CANONICAL_SCHEMA_CHANGED")
    gaps=scan(mail[1:])
    evidence=[]
    for book,tab,area,pk,hk,nk in SOURCES:
        evidence.append((tab,rows(read(session,book,tab,area)),pk,hk,nk))
    reconciled=compare(gaps,evidence)
    print("MULTISOURCE_INVOICE_PARITY "+json.dumps({
        "gap_count":len(gaps),"sources":{x[0]:len(x[1]) for x in evidence},
        "statuses":dict(Counter(r["status"] for r in reconciled)),
        "records":reconciled,"owner_verified":False,"batch_invoice_verified":False,
        "confirmed_unissued":0},ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
