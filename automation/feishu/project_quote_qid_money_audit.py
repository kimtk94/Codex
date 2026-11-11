#!/usr/bin/env python3
"""Read-only, exact AMEA->Quote Portfolio->SFDC QID->USD price evidence audit.

This diagnoses whether Quote Name centered project records can safely display an
actual SFDC Quote amount. Historical portfolio amount units are NOT assumed USD;
the subscribed process report's received time is NOT its export time.
No customer or money values are logged; no Feishu or Sheets write operations.
"""
from __future__ import annotations
import collections
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import json
import os
import re
import urllib.parse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from sales_home_links import API, PROJECT_BOARD, pages, request, extract_token, require
from sfdc_quote_report_bridge import verify_qq_process_report_audit

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TABS = {
    "portfolio": ("Quote Portfolio", "A1:AZ3000"),
    "headers": ("SFDC Quote Export", "A1:AZ3000"),
    "products": ("SFDC Email Quotation Raw", "A1:AZ5000"),
    "audit": ("SFDC Email Ingest Audit", "A1:AZ50"),
}
KST = timezone(timedelta(hours=9))
QID_RE = re.compile(r"^QID-[0-9-]{8,50}$", re.IGNORECASE)
SFID_RE = re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
AMEA_RE = re.compile(r"^AMEA\d{7,}(?:-\d{1,3})?$", re.IGNORECASE)

def text(v):
    if v is None: return ""
    if isinstance(v,str): return v.strip()
    if isinstance(v,dict):return str(v.get("text") or v.get("value") or v.get("name") or "").strip()
    if isinstance(v,list):return " ".join(text(s) for s in v).strip()
    return str(v).strip()

def numeric(v):
    v=text(v).replace(",","")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",v):
        return None
    try:
        d=Decimal(v)
        return d if d.is_finite() else None
    except InvalidOperation:
        return None

def sfid(v):
    v=text(v)
    return v[:15].lower() if SFID_RE.fullmatch(v) else ""

def read_rows(session, name, address):
    target=urllib.parse.quote("'"+name.replace("'","''")+"'!"+address,safe="")
    uri="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+"/values/"+target
    response=session.get(uri,timeout=55)
    if response.status_code!=200:
        raise RuntimeError("SHEETS_SOURCE_UNAVAILABLE_"+name.replace(" ","_"))
    matrix=response.json().get("values") or []
    if not matrix:raise RuntimeError("EMPTY_SOURCE_"+name.replace(" ","_"))
    head=[str(s).strip() for s in matrix[0]]
    if not head or len(head)!=len(set(head)):
        raise RuntimeError("INVALID_SOURCE_HEADERS")
    records=[]
    for r in matrix[1:]:
        if any(text(s) for s in r):
            records.append({k:text(r[i]) if i<len(r) else "" for i,k in enumerate(head)})
    return records,head

def portfolio_index(rows):
    by_amea=collections.defaultdict(list)
    for r in rows:
        amea=text(r.get("Approved AMEA ID")).upper()
        if AMEA_RE.fullmatch(amea):
            by_amea[amea].append(r)
    return by_amea

def quote_reference(board_row, source_rows):
    """Require exact project-name and AMEA matches, approved and active source."""
    f=board_row.get("fields") or {}
    quote_name=text(f.get("Quote Full Name"))
    amea=text(f.get("AMEA")).upper()
    source_state=text(f.get("Quote Match State"))
    if source_state!="SFDC_EXACT_VERIFIED":
        return None, "PROJECT_QUOTE_NOT_EXACT_VERIFIED"
    exact=[r for r in source_rows if text(r.get("Quote Name"))==quote_name]
    if not exact:
        return None, "PORTFOLIO_NAME_MISMATCH"
    accepted=[r for r in exact if text(r.get("Approval Match")).upper()=="APPROVED"
              and text(r.get("Active")).upper() in ("ACTIVE","YES","TRUE","1")]
    if not accepted:
        return None, "PORTFOLIO_NOT_ACTIVE_APPROVED"
    ids={(text(r.get("Quote QID")).upper(),sfid(r.get("Salesforce Quote ID (18)")))
         for r in accepted}
    if len(ids)!=1:
        return None, "PORTFOLIO_AMBIGUOUS_QID_OR_RECORD"
    qid,rid=next(iter(ids))
    if not QID_RE.fullmatch(qid) or not rid:
        return None, "PORTFOLIO_IDENTIFIERS_INVALID"
    vals={numeric(r.get("Quote USD")) for r in accepted}
    if len(vals)!=1 or None in vals:
        return None, "PORTFOLIO_AMOUNT_CONFLICT"
    return {"amea":amea,"name":quote_name,"qid":qid,"record_id":rid,
            "portfolio_value":next(iter(vals))}, "QID_REFERENCE_EXACT"

def header_index(rows):
    grouped=collections.defaultdict(list)
    for row in rows:
        qid=text(row.get("AMEA Quotation ID")).upper()
        if qid:grouped[qid].append(row)
    return grouped

def price_evidence(candidate,headers):
    group=headers.get(candidate["qid"],[])
    if len(group)!=1:return "SFDC_EXPORT_MISSING_OR_DUPLICATE",None
    row=group[0]
    if sfid(row.get("Salesforce Record ID")) != candidate["record_id"]:
        return "SFDC_RECORD_ID_MISMATCH",None
    currency=text(row.get("CurrencyIsoCode")).upper()
    active=text(row.get("IsActive")).upper()
    if active not in ("TRUE","YES","1"):
        return "SFDC_EXPORT_NOT_ACTIVE",None
    reported=numeric(row.get("Exclude Tax After Discount USD"))
    if reported is None or reported<0:return "SFDC_EXPORT_AMOUNT_UNAVAILABLE",None
    if currency not in ("KRW","USD"):
        return "SFDC_EXPORT_CURRENCY_MISSING",None
    # This source must be checked for actual quote currency and reliable rates.
    historic=candidate["portfolio_value"]
    ratio=historic/reported if reported>0 else None
    if ratio is None:return "SFDC_EXPORT_ZERO_OR_MISSING",None
    if abs(ratio-1)<Decimal("0.02"):parity="RATIO_NEAR_1"
    elif abs(ratio-Decimal("1500"))<=Decimal("75"):parity="RATIO_NEAR_1500"
    else:parity="RATIO_OTHER"
    # Validation is a diagnostic, not permission to convert currency.
    return "REFERENCE_ONLY_"+parity+"_"+currency,reported

def audit(board,portfolio,header_rows,source_age,header_age):
    ref=portfolio_index(portfolio)
    hdr=header_index(header_rows)
    statuses=collections.Counter()
    match_by_view=collections.Counter()
    candidate_ids=set()
    historical_ratios=collections.Counter()
    valid=0
    for record in board:
        f=record.get("fields") or {}
        code=text(f.get("AMEA")).upper()
        candidate,state=quote_reference(record,ref.get(code,[]))
        statuses[state]+=1
        if candidate is None:continue
        valid+=1
        candidate_ids.add(candidate["qid"])
        evidence,_=price_evidence(candidate,hdr)
        historical_ratios[evidence]+=1
    summary={
        "projects":len(board),"portfolio_rows":len(portfolio),
        "reference_exact_rows":valid,"distinct_reference_qids":len(candidate_ids),
        "reference_issue_counts":dict(sorted(statuses.items())),
        "quote_amount_evidence_counts":dict(sorted(historical_ratios.items())),
        "source_mail_receipt_age_hours":source_age,
        "header_export_age_days":header_age,
        "quote_amount_verified_rows":0,
        "monetary_write_count":0,
        "safe_to_display_final_quote_amount":False,
    }
    return summary

def main():
    raw=require("GCP_SERVICE_ACCOUNT_JSON")
    sa=service_account.Credentials.from_service_account_info(json.loads(raw),
                  scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(sa)
    sources={key:read_rows(session,*parts) for key,parts in TABS.items()}
    # Verify the latest 25-column QQ mail snapshot was not altered in Sheets.
    proof=verify_qq_process_report_audit(sources["products"],sources["audit"])
    now=datetime.now(KST)
    receipt=datetime.strptime(proof["received_kst"],"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
    stamp_values={text(r.get("Exported At KST")) for r in sources["headers"][0] if text(r.get("Exported At KST"))}
    if len(stamp_values)!=1:raise RuntimeError("SFDC_EXPORT_TIMESTAMP_AMBIGUOUS")
    exported=datetime.strptime(next(iter(stamp_values)),"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
    receipt_age=round((now-receipt).total_seconds()/3600,2)
    export_age=round((now-exported).total_seconds()/86400,2)
    auth=extract_token(request("POST","/open-apis/auth/v3/tenant_access_token/internal",
                body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")}))
    board=list(pages(API+"/tables/"+PROJECT_BOARD+"/records",auth))
    if not board:raise RuntimeError("PROJECT_BOARD_EMPTY")
    report=audit(board,sources["portfolio"][0],sources["headers"][0],receipt_age,export_age)
    print("PROJECT_QUOTE_QID_MONEY_AUDIT",json.dumps(report,ensure_ascii=False,sort_keys=True))
    print("SOURCE_HASH_VERIFIED=1 SOURCE_RECORDS_WRITTEN=0 PROJECT_RECORDS_WRITTEN=0")
if __name__=="__main__":main()
