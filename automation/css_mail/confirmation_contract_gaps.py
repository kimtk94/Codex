#!/usr/bin/env python3
"""Contract-level notice gaps. Does not certify confirmation or personal revenue."""
import json,os,re,urllib.parse
from collections import defaultdict
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from canonical_confirmation_audit import classify,BOOK

AMEA=re.compile(r"AMEA[0-9]{7,}",re.I)
CONTRACT=re.compile(r"H[0-9]{3}SC[0-9]{5,}|H[0-9]{5,}",re.I)
SAM=re.compile(r"SAM[0-9]{7,}",re.I)
INVOICE=re.compile(r"209126[0-9]{6}")
def scan(rows):
    result=defaultdict(lambda:{"ready":set(),"issued":set(),"sam":set(),"invoice":set()})
    for row in rows:
        def v(i):return str(row[i]) if i<len(row) else ""
        state=classify(v(14))
        if not state:continue
        text=" ".join((v(14),v(17),v(18),v(19)))
        projects={x.upper() for x in AMEA.findall(text)}
        contracts={x.upper() for x in CONTRACT.findall(text)} or {"H_UNSPECIFIED"}
        for project in projects:
            for contract in contracts:
                rec=result[(project,contract)]
                rec["ready" if state=="STATEMENT_READY_NOTICE" else "issued"].add(v(0))
                rec["sam"].update(x.upper() for x in SAM.findall(text))
                rec["invoice"].update(INVOICE.findall(text))
    return sorted(({"amea":p,"contract":h,"sam":sorted(r["sam"]),
        "invoice_numbers_in_subject":sorted(r["invoice"]),
        "ready_count":len(r["ready"]),"issued_count":len(r["issued"]),
        "status":"REVIEW_NO_ISSUED_NOTICE"} for (p,h),r in result.items()
        if r["ready"] and not r["issued"]),key=lambda r:(r["amea"],r["contract"]))
def main():
    c=service_account.Credentials.from_service_account_info(json.loads(os.environ["CKD_DRIVE_SA_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s=AuthorizedSession(c)
    a=urllib.parse.quote("'Canonical Mail Ledger'!A1:AA60000",safe="")
    r=s.get("https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+a,timeout=90)
    r.raise_for_status()
    values=r.json().get("values",[])
    if not values or len(values[0])<27 or values[0][14]!="subject":
        raise RuntimeError("CANONICAL_SCHEMA_CHANGED")
    records=scan(values[1:])
    print("CANONICAL_CONTRACT_NOTICE_GAPS "+json.dumps({"count":len(records),"items":records,"owner_verified":False,"customer_confirmed":False},ensure_ascii=False))
if __name__=="__main__":main()
