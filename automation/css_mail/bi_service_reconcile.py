#!/usr/bin/env python3
"""Idempotent, fail-closed BI service reconciliation from approved invoice map.

Only approved classification (D) and basis/status (H) may be updated.
Summary uses protected live VAT-excluded formulas; source gross and canonical evidence are immutable.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SHEET = os.getenv("BI_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
CANONICAL = "BI Service Canonical Map"
FACT = "BI Service 8 Fact"
SUMMARY = "BI Service 8 Summary"
BASE = "Revenue Invoice Base"
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

def invoice_net(gross):
    value=Decimal(str(number(gross)))/Decimal("1.1")
    return int(value.quantize(Decimal("1"),rounding=ROUND_HALF_UP))


def source_parity(base,fact,allow_missing=False):
    """Always validate matched invoices; optionally stage new verified originals."""
    if not base or len(base[0])<14 or base[0][0]!="Invoice No" or base[0][13]!="Net Revenue KRW (VAT excl; per invoice)":
        raise RuntimeError("BASE_NET_SCHEMA_INVALID")
    if not fact or len(fact[0])<12 or fact[0][10:12]!=["Net Revenue KRW (VAT excl)","Net Revenue K USD (VAT excl)"]:
        raise RuntimeError("FACT_NET_SCHEMA_INVALID")
    source={}
    for row in base[1:]:
        if not row or not row[0]:continue
        if len(row)<14:raise RuntimeError("BASE_NET_MISSING")
        invoice=str(row[0])
        if invoice in source:raise RuntimeError("BASE_DUPLICATE_INVOICE")
        gross,net=number(row[3]),number(row[13])
        if invoice_net(gross)!=net:raise RuntimeError("BASE_NET_AMOUNT_MISMATCH")
        source[invoice]=(gross,net,float(row[12]),str(row[1]))
    seen=set()
    for r in fact[1:]:
        if not r or not r[0]:continue
        invoice=str(r[0])
        if invoice in seen:raise RuntimeError("DUPLICATE_FACT_INVOICE")
        seen.add(invoice)
        if invoice not in source:raise RuntimeError("FACT_NOT_IN_VERIFIED_BASE")
        gross,net,kusd,month=source[invoice]
        if (len(r)<12 or number(r[5])!=gross or number(r[10])!=net
                or abs(float(r[11])-kusd)>0.000001 or str(r[1])!=month):
            raise RuntimeError("FACT_INVOICE_NET_OR_GROSS_MISMATCH")
    if set(source)!=seen and not allow_missing:
        raise RuntimeError("SOURCE_INVOICE_NOT_IN_FACT count="+str(len(set(source)-seen)))
    if not source:raise RuntimeError("EMPTY_VERIFIED_INVOICE_BASE")
    return source


def plan_new_review_rows(base,fact,fx,stamped):
    """Build append-only review rows from the original verified Invoice base.

    Never assign an approved service or modify the canonical classification.
    Existing rows must be contiguous; partial or conflicting data fails closed.
    """
    if not fx or Decimal(str(fx))<=0:
        raise RuntimeError("REPORTING_FX_INVALID")
    source=source_parity(base,fact,allow_missing=True)
    existing=set()
    empty_started=False
    for r in fact[1:]:
        if not r or not r[0]:
            empty_started=True
            continue
        if empty_started:
            raise RuntimeError("FACT_NONCONTIGUOUS_ROWS")
        existing.add(str(r[0]))
    added=[]
    for r in base[1:]:
        if not r or not r[0] or str(r[0]) in existing:
            continue
        invoice=str(r[0])
        if len(r)<14 or not str(r[1]).strip() or not str(r[4]).strip() or not str(r[7]).strip():
            raise RuntimeError("SOURCE_INVOICE_METADATA_INCOMPLETE")
        if not re.fullmatch(r"[0-9]{10,15}",invoice):
            raise RuntimeError("SOURCE_INVOICE_NUMBER_INVALID")
        gross,net,_,month=source[invoice]
        if month!=str(r[1]):
            raise RuntimeError("SOURCE_INVOICE_MONTH_CONFLICT")
        if str(r[10]).strip()=="":
            raise RuntimeError("SOURCE_L4_MISSING")
        row=[invoice,month,str(r[4]),"Review / Other",str(r[10]),gross,
             float(Decimal(gross)/Decimal(str(fx))/Decimal(1000)),
             "SOURCE_NEW_REVIEW_"+stamped,str(r[7]),""]
        added.append(row)
    if len(added)!=len(set(source)-existing):
        raise RuntimeError("SOURCE_APPEND_PLAN_INCOMPLETE")
    return added


def verify_summary(summary,expected):
    header=["Service Group","Invoice Count","Net Revenue KRW (VAT excl)","Net Revenue K USD (VAT excl)"]
    if not summary or summary[0]!=header or len(summary)-1!=len(expected):
        raise RuntimeError("SUMMARY_NET_SCHEMA_MISMATCH")
    for got,want in zip(summary[1:],expected):
        if (len(got)<4 or got[0]!=want[0] or number(got[1])!=want[1]
                or number(got[2])!=want[2] or abs(float(got[3])-want[3])>0.000001):
            raise RuntimeError("SUMMARY_NET_AMOUNT_MISMATCH category="+want[0])


def main():
    info=json.loads(os.environ["CKD_DRIVE_SA_JSON"])
    cred=service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session=AuthorizedSession(cred)
    meta=api(session,"GET","?fields=sheets.properties(sheetId,title,gridProperties(rowCount))")
    sheets={r["properties"]["title"]:r["properties"] for r in meta.get("sheets",[])}
    for name in (CANONICAL,FACT,SUMMARY,BASE):
        if name not in sheets: raise RuntimeError("MISSING_TAB_"+name)
    cm=read(session,CANONICAL,"A1:H1000")
    fact=read(session,FACT,"A1:L1000")
    base=read(session,BASE,"A1:N1000")
    source=source_parity(base,fact,allow_missing=True)
    fx_data=read(session,"Revenue FX Settings","A1:B3")
    if len(fx_data)<2 or len(fx_data[1])<2:
        raise RuntimeError("REPORTING_FX_SOURCE_MISSING")
    fx=Decimal(str(fx_data[1][1]).replace(",",""))
    new_rows=plan_new_review_rows(base,fact,fx,dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d"))
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
        if len(r)<12: raise RuntimeError("INCOMPLETE_FACT_RECORD")
        service=r[3]
        if invoice in canonical:
            approved,amount,basis=canonical[invoice]
            if number(r[5])!=amount:
                raise RuntimeError("AMOUNT_CONFLICT_FOR_INVOICE_SUFFIX_"+invoice[-4:])
            if service!=approved:
                changes.append((row_i,approved,basis))
                service=approved
        if service not in CATEGORIES: raise RuntimeError("UNKNOWN_SERVICE_CATEGORY")
        if invoice not in canonical and (service!="Review / Other" or not str(r[7]).startswith("SOURCE_NEW_REVIEW_")):
            raise RuntimeError("NEW_INVOICE_REQUIRES_CLASSIFICATION_REVIEW")
        rows.append((service,number(r[10]),float(r[11])))
    if not rows or len(rows)!=len(seen):
        raise RuntimeError("EMPTY_OR_INVALID_FACT")
    for r in new_rows:
        rows.append((r[3],invoice_net(r[5]),float(Decimal(invoice_net(r[5]))/fx/Decimal(1000))))
    if len(rows)!=len(source):
        raise RuntimeError("NEW_INVOICE_PLAN_PARITY_FAILED")
    # All checks complete before writing. All changes are one atomic batch.
    requests=[]
    for i,category,basis in changes:
        requests.append({"updateCells":{"start":{"sheetId":sheets[FACT]["sheetId"],"rowIndex":i,"columnIndex":3},
            "rows":[{"values":[user_value(category)]}],"fields":"userEnteredValue"}})
        requests.append({"updateCells":{"start":{"sheetId":sheets[FACT],"rowIndex":i,"columnIndex":7},
            "rows":[{"values":[user_value("CANONICAL_RESTORED:"+basis[:100])]}],"fields":"userEnteredValue"}})
    if new_rows:
        next_row=len(fact)
        if next_row-1 != len(seen):
            raise RuntimeError("FACT_APPEND_POSITION_UNSAFE")
        max_rows=int(sheets[FACT].get("gridProperties",{}).get("rowCount",0))
        if not max_rows:
            raise RuntimeError("FACT_GRID_BOUNDS_UNKNOWN")
        overflow=max(0,next_row+len(new_rows)-max_rows)
        if overflow:
            requests.insert(0,{"appendDimension":{
                "sheetId":sheets[FACT]["sheetId"],"dimension":"ROWS","length":overflow}})
        requests.append({"updateCells":{
            "start":{"sheetId":sheets[FACT]["sheetId"],"rowIndex":next_row,"columnIndex":0},
            "rows":[{"values":[user_value(v) for v in row]} for row in new_rows],
            "fields":"userEnteredValue"}})
    totals=collections.defaultdict(lambda:[0,0,0.0])
    for category,amount,kusd in rows:
        totals[category][0]+=1
        totals[category][1]+=amount
        totals[category][2]+=kusd
    new_summary=[[k,*totals[k]] for k in CATEGORIES]
    if sum(x[1] for x in new_summary)!=len(rows):
        raise RuntimeError("TOTAL_COUNT_MISMATCH")
    # The summary is formula-owned, not a writable static output. Existing
    # manual classification remains in Fact D/H; never replace formula columns.
    if requests:
        api(session,"POST",":batchUpdate",json={"requests":requests})
    if new_rows:
        # Re-read the actual live calculated K/L values. The next scheduled
        # run can safely retry if formula recalculation is temporarily delayed.
        actual_fact=read(session,FACT,"A1:L1000")
        source_parity(base,actual_fact)
    verify_summary(read(session,SUMMARY,"A1:D20"),new_summary)
    print("BI_SERVICE_RECONCILE_PASS canonical="+str(len(canonical))+
          " fact="+str(len(rows))+" restored="+str(len(changes))+
          " net_revenue_krw="+str(sum(x[1] for x in rows))+
          " new_review="+str(len(new_rows))+
          " requests="+str(len(requests)),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("BI_SERVICE_RECONCILE_FAILED "+str(exc),file=sys.stderr)
        sys.exit(1)
