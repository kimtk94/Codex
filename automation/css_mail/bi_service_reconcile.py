#!/usr/bin/env python3
"""Idempotent, fail-closed BI service reconciliation from approved invoice map.

Only classification (D), basis/status (H), and 8 Summary numbers are updated.
Never changes invoice source fields, email, revenue amounts, or canonical map.
"""
import collections
from decimal import Decimal
import datetime as dt
import json
import os
import sys
import urllib.parse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SHEET = os.getenv("BI_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
CANONICAL = "BI Service Canonical Map"
FACT = "BI Service 8 Fact"
SUMMARY = "BI Service 8 Summary"
CATEGORIES = (
    "WGS/WES", "mRNA", "ncRNA", "scRNA", "PMP/PML", "LC-MS",
    "Epigenomics", "Metagenome", "Long-read", "Olink", "Review / Other"
)

def api(session, method, path, **kwargs):
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET + path
    response = session.request(method, url, timeout=65, **kwargs)
    if not response.ok:
        raise RuntimeError("SHEETS_STATUS_" + str(response.status_code))
    return response.json() if response.content else {}

def quote_range(name, coordinates):
    return urllib.parse.quote("'" + name + "'!" + coordinates, safe="")

def number(raw):
    return int(str(raw).strip().replace(",", ""))

def read(session, name, coordinates):
    rows = api(session, "GET", "/values/" + quote_range(name, coordinates)).get("values", [])
    if not rows:
        raise RuntimeError("EMPTY_TAB_" + name)
    return rows

def user_value(value):
    return {"userEnteredValue": {"numberValue":value} if isinstance(value,(int,float))
            else {"stringValue":str(value)}}

def net_summary_from_gross_fact(rows):
    """Preserve VAT-exclusive Summary from VAT-inclusive Fact, never write gross as net."""
    totals=collections.defaultdict(lambda:[0,0,Decimal("0")])
    for category,amount,kusd in rows:
        if category not in CATEGORIES or amount<0:
            raise RuntimeError("INVALID_GROSS_FACT_RECORD")
        totals[category][0]+=1
        totals[category][1]+=amount
        totals[category][2]+=Decimal(str(kusd))
    result=[]
    for category in CATEGORIES:
        n,gross,usd_gross=totals[category]
        net_numerator=gross*10
        if net_numerator%11:
            raise RuntimeError("VAT_NET_NOT_EXACT_INTEGER_FOR_"+category)
        result.append([category,n,net_numerator//11,float(usd_gross*Decimal(10)/Decimal(11))])
    return result

def main():
    info=json.loads(os.environ["CKD_DRIVE_SA_JSON"])
    cred=service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session=AuthorizedSession(cred)
    meta=api(session,"GET","?fields=sheets.properties(sheetId,title)")
    sheets={r["properties"]["title"]:r["properties"]["sheetId"] for r in meta.get("sheets",[])}
    for name in (CANONICAL,FACT,SUMMARY):
        if name not in sheets: raise RuntimeError("MISSING_TAB_"+name)
    cm=read(session,CANONICAL,"A1:H1000")
    fact=read(session,FACT,"A1:I1000")
    expected_c=["Invoice Number","Canonical Service","Original L4","Rule Basis","AMEA Project ID","Invoice Month","Revenue KRW","Validation"]
    expected_f=["Invoice Number","Invoice Month","Institution","Service (8 groups)","Original L4","Revenue KRW","Revenue K USD","Mapping Status","AMEA Project ID"]
    if cm[0]!=expected_c or fact[0][:9]!=expected_f:
        raise RuntimeError("SCHEMA_MISMATCH_MANUAL_REVIEW")
    canonical={}
    for r in cm[1:]:
        if not r or not r[0]: continue
        invoice=r[0]
        if invoice in canonical: raise RuntimeError("DUPLICATE_CANONICAL")
        if len(r)<8 or r[1] not in CATEGORIES or r[7]!="VERIFIED_FROM_BI_FACT":
            raise RuntimeError("BAD_CANONICAL_RECORD")
        canonical[invoice]=(r[1],number(r[6]),r[3])
    if len(canonical)<327:
        raise RuntimeError("CANONICAL_TOO_SMALL")
    rows=[]
    changes=[]
    seen=set()
    for row_i,r in enumerate(fact[1:],start=1):
        if not r or not r[0]: continue
        invoice=r[0]
        if invoice in seen: raise RuntimeError("DUPLICATE_FACT_INVOICE")
        seen.add(invoice)
        if len(r)<9: raise RuntimeError("INCOMPLETE_FACT_RECORD")
        service=r[3]
        if invoice in canonical:
            approved,amount,basis=canonical[invoice]
            if number(r[5])!=amount:
                raise RuntimeError("AMOUNT_CONFLICT_FOR_INVOICE_SUFFIX_"+invoice[-4:])
            if service!=approved:
                changes.append((row_i,approved,basis))
                service=approved
        if service not in CATEGORIES: raise RuntimeError("UNKNOWN_SERVICE_CATEGORY")
        rows.append((service,number(r[5]),float(r[6])))
    if not rows or len(rows)!=len(seen):
        raise RuntimeError("EMPTY_OR_INVALID_FACT")
    # All checks complete before writing. All changes are one atomic batch.
    requests=[]
    for i,category,basis in changes:
        requests.append({"updateCells":{"start":{"sheetId":sheets[FACT],"rowIndex":i,"columnIndex":3},
            "rows":[{"values":[user_value(category)]}],"fields":"userEnteredValue"}})
        requests.append({"updateCells":{"start":{"sheetId":sheets[FACT],"rowIndex":i,"columnIndex":7},
            "rows":[{"values":[user_value("CANONICAL_RESTORED:"+basis[:100])]}],"fields":"userEnteredValue"}})
    new_summary=net_summary_from_gross_fact(rows)
    old_summary=read(session,SUMMARY,"A1:D20")
    if old_summary[0]!=[
        "Service Group","Invoice Count","Net Revenue KRW (VAT excl)",
        "Net Revenue K USD (VAT excl)"
    ]:
        raise RuntimeError("SUMMARY_SCHEMA_MISMATCH_OR_UNKNOWN_TAX_BASIS")
    if sum(x[1] for x in new_summary)!=len(rows):
        raise RuntimeError("TOTAL_COUNT_MISMATCH")
    if changes or len(old_summary)-1!=len(new_summary) or any(
        i>=len(old_summary)-1 or old_summary[i+1][0]!=r[0] or
        number(old_summary[i+1][1])!=r[1] or number(old_summary[i+1][2])!=r[2] or
        len(old_summary[i+1])<4 or abs(float(old_summary[i+1][3])-r[3])>1e-6
        for i,r in enumerate(new_summary)
    ):
        requests.append({"updateCells":{"start":{"sheetId":sheets[SUMMARY],"rowIndex":1,"columnIndex":0},
            "rows":[{"values":[user_value(v) for v in row]} for row in new_summary],
            "fields":"userEnteredValue"}})
    if requests:
        api(session,"POST",":batchUpdate",json={"requests":requests})
    print("BI_SERVICE_RECONCILE_PASS canonical="+str(len(canonical))+
          " fact="+str(len(rows))+" restored="+str(len(changes))+
          " revenue_krw="+str(sum(x[1] for x in rows))+
          " requests="+str(len(requests)),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("BI_SERVICE_RECONCILE_FAILED "+str(exc),file=sys.stderr)
        sys.exit(1)
