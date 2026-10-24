#!/usr/bin/env python3
"""Reconcile issued Tax Invoice with Feishu project forecasts; no public row-level logs."""
import collections
import datetime as dt
import re
import urllib.parse
from invoice_reconciliation import norm_id
from project_status_sync import api, sheet, values
from online_project_tat_forecast import FX, KST

INVOICE_TAB = "Revenue Invoice Base"
FORECAST_TAB = "Feishu Project TAT Forecast"
OUTPUT_TAB = "BI Revenue Actual Forecast"
REVIEW_TAB = "BI Revenue Duplicate Review"
SOURCE_RANGE = {
    INVOICE_TAB: "A1:M1800",
    FORECAST_TAB: "A1:S2000",
}
MONTHLY_HEADER = ["Month","Issued Tax Invoice KRW","Issued Tax Invoice K USD",
                  "Net Project Forecast KRW","Net Project Forecast K USD",
                  "Combined KRW","Combined K USD","Issued Invoice Count",
                  "Forecast Project Count","Automatically Deduplicated",
                  "Needs Invoice Mapping Review","Data As Of KST"]
REVIEW_HEADER = ["Contract Number","Sub-Project Number","Staging Number",
                 "Forecast Month","Planned KRW","Issued Invoice Count",
                 "Matched Invoice KRW","Decision","Reason","Invoice Months"]
STRONG = "MATCH_H_AND_AMEA"
NO_MATCH = "NO_INVOICE_MATCH"

def read(session,tab):
    path=urllib.parse.quote("'"+tab+"'!"+SOURCE_RANGE[tab],safe="")
    return api(session,"GET","/values/"+path).get("values",[])

def objects(rows,needed):
    if not rows:raise RuntimeError("SOURCE_TAB_EMPTY")
    names=rows[0]
    if any(k not in names for k in needed):
        raise RuntimeError("SOURCE_SCHEMA_MISSING")
    return [dict(zip(names,r)) for r in rows[1:] if any(str(x).strip() for x in r)]

def money(value):
    s=str(value or "").replace(",","").replace("₩","").strip()
    if not s:return None
    try:
        n=float(s)
    except ValueError:
        return None
    if not (0 <= n < 1e14):return None
    return n

def mea_from_title(title):
    # Require whole AMEA identifier, not a contract name or fuzzy institution match.
    found=re.findall(r"(?<![A-Z0-9])AMEA\d{6,}(?:[-_]\d+)?(?![A-Z0-9])",str(title or "").upper())
    return norm_id(found[0]) if len(found)==1 else ""

def resolution(project,invoices_by_h):
    contract=norm_id(project.get("Contract Number"))
    mea=mea_from_title(project.get("Contract Name"))
    matched=invoices_by_h.get(contract,[])
    if not matched:
        return NO_MATCH,[],False
    exact=[i for i in matched if mea and i["_amea"]==mea]
    if not mea or not exact:
        return "REVIEW_H_ONLY_OR_CONFLICT",matched,False
    if any(i["_amea"]!=mea for i in matched):
        # Multiple AMEA IDs on same H contract: cannot attribute billed amount to a stage.
        return "REVIEW_CONTRACT_MULTIPLE_AMEA",matched,False
    stage=str(project.get("Staging Number") or "").upper()
    # Only first/sole stage may be automatically netted against contract-level invoices.
    # F002+ is an additional stage and cannot be inferred from prior billing.
    if project.get("Forecast Category") == "COMPLETED" and (not re.search(r"-F\\d{3}$",stage) or stage.endswith("-F001")):
        return "DEDUPE_ISSUED_COMPLETED",exact,True
    # Historic invoices might relate to earlier stage, e.g., F001 vs F002/F005.
    return "REVIEW_PARTIAL_OR_PRIOR_STAGE",exact,False

def reconcile_rows(invoice_rows,project_rows,snapshot):
    invoices=objects(invoice_rows,["Invoice No","Year-Month","Revenue KRW (Tax Invoice)","AMEA ID","H Project ID"])
    projects=objects(project_rows,["Contract Number","Contract Name","Sub-Project Number",
        "Staging Number","Forecast Completion Month","Forecast Category","Projected KRW @1500"])
    by_num={}
    for inv in invoices:
        invoice_no=norm_id(inv.get("Invoice No"))
        amount=money(inv.get("Revenue KRW (Tax Invoice)"))
        month=str(inv.get("Year-Month") or "")[:7]
        if not invoice_no or amount is None or not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])",month):
            raise RuntimeError("INVALID_ISSUED_INVOICE_DATA")
        signature=(month,amount,norm_id(inv.get("H Project ID")),norm_id(inv.get("AMEA ID")))
        if invoice_no in by_num and by_num[invoice_no]["_signature"] != signature:
            raise RuntimeError("DUPLICATE_INVOICE_CONFLICT")
        saved=dict(inv,_number=invoice_no,_amount=amount,_month=month,
                   _h=norm_id(inv.get("H Project ID")),_amea=norm_id(inv.get("AMEA ID")),
                   _signature=signature)
        by_num[invoice_no]=saved
    issued=list(by_num.values())
    invoice_by_h=collections.defaultdict(list)
    by_month=collections.defaultdict(lambda:collections.Counter())
    for inv in issued:
        if inv["_h"]:invoice_by_h[inv["_h"]].append(inv)
        by_month[inv["_month"]]["actual"]+=inv["_amount"]
        by_month[inv["_month"]]["invoices"]+=1
    reviews=[REVIEW_HEADER]
    seen_project=set()
    decision_counts=collections.Counter()
    # Do not automatically attribute a single invoice to multiple staging rows.
    project_h_counts=collections.Counter(norm_id(p.get("Contract Number")) for p in projects)
    for project in projects:
        project_key=(norm_id(project.get("Contract Number")),norm_id(project.get("Staging Number")),
                     norm_id(project.get("Sub-Project Number")))
        if project_key in seen_project:raise RuntimeError("DUPLICATED_PROJECT_KEY")
        seen_project.add(project_key)
        month=str(project.get("Forecast Completion Month") or "")[:7]
        category=str(project.get("Forecast Category") or "")
        planned=money(project.get("Projected KRW @1500"))
        decision,candidates,dedup=resolution(project,invoice_by_h)
        if candidates and project_h_counts[project_key[0]]>1:
            decision="REVIEW_MULTIPLE_STAGING";dedup=False
        decision_counts[decision]+=1
        if category not in ("FORECAST","COMPLETED"):
            # No projected value for excluded/pending source records.
            continue
        if planned is None or not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])",month):
            raise RuntimeError("INVALID_PROJECT_FORECAST")
        if dedup:
            by_month[month]["dedup"]+=1
        else:
            by_month[month]["forecast"]+=planned
            by_month[month]["forecast_projects"]+=1
        if decision.startswith("REVIEW_"):
            by_month[month]["review"]+=1
        if decision!=NO_MATCH:
            reviews.append([project.get("Contract Number",""),project.get("Sub-Project Number",""),
                project.get("Staging Number",""),month,round(planned),
                len(candidates),round(sum(i["_amount"] for i in candidates)),
                decision,"Invoice issuance proven by identifiers; stage attribution requires review"
                if not dedup else "Exact H + AMEA on completed-status project",
                ", ".join(sorted(set(i["_month"] for i in candidates)))])
    monthly=[MONTHLY_HEADER]
    for month,v in sorted(by_month.items()):
        actual=round(v["actual"]);forecast=round(v["forecast"])
        monthly.append([month,actual,round(actual/FX/1000,3),
            forecast,round(forecast/FX/1000,3),
            actual+forecast,round((actual+forecast)/FX/1000,3),
            v["invoices"],v["forecast_projects"],v["dedup"],v["review"],snapshot])
    return monthly,reviews,decision_counts

def publish(session):
    snapshot=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    invoices=read(session,INVOICE_TAB)
    forecast=read(session,FORECAST_TAB)
    monthly,reviews,counts=reconcile_rows(invoices,forecast,snapshot)
    sheet(session,OUTPUT_TAB);sheet(session,REVIEW_TAB)
    meta=api(session,"GET","?fields=sheets.properties")
    requests=[]
    for x in meta.get("sheets",[]):
        p=x.get("properties") or {}
        desired=14 if p.get("title") in (OUTPUT_TAB,REVIEW_TAB) else None
        if desired and (p.get("gridProperties") or {}).get("columnCount",0)<desired:
            requests.append({"updateSheetProperties":{"properties":{"sheetId":p["sheetId"],
                "gridProperties":{"columnCount":desired}},"fields":"gridProperties.columnCount"}})
    if requests:api(session,"POST",":batchUpdate",json={"requests":requests})
    # Clear generated tabs only, never invoice source or manually maintained tabs.
    for name in (OUTPUT_TAB,REVIEW_TAB):
        span=urllib.parse.quote("'"+name+"'!A1:N2000",safe="")
        api(session,"POST","/values/"+span+":clear",json={})
    values(session,OUTPUT_TAB,"A1",monthly)
    values(session,REVIEW_TAB,"A1",reviews)
    print("INVOICE_FORECAST_RECONCILIATION_PASS months="+str(len(monthly)-1)+
          " review_rows="+str(len(reviews)-1)+
          " dedup="+str(counts["DEDUPE_ISSUED_COMPLETED"]))
    print("INVOICE_SOURCE_WRITES: 0; FEISHU_WRITES: 0; ROW_LOGGING: DISABLED")
