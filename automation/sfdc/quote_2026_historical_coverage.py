#!/usr/bin/env python3
"""Aggregate 2026 historical approval coverage from QQ + Quotation Approvals.

GitHub Actions can verify *eligibility counts and source SHA*, never native KRW prices.
The authenticated SFDC browser that reads original KRW unit prices is a separate,
private local workflow. No customer IDs, names or prices in public CI output.
"""
from collections import Counter,defaultdict
from datetime import datetime
import argparse,json,re
from pathlib import Path

QID=re.compile(r"^QID-2026-\d{2}-\d{2}-\d{4,}$")
RECORD=re.compile(r"^a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
PROCESS=re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
APPROVAL_COLUMNS={"approved_at_kst","quotation_created_date","quotation_name",
                  "quotation_id","salesforce_record_id"}
REPORT_COLUMNS={"SFDC Quotation ID","Quotation Product ID","Active","Created Date",
                "Process Name: SFDC Process ID","Quote Process Name"}
CUTOFF="2026-10-19"

def source_date(text):
    try:
        return datetime.strptime(text,"%m/%d/%Y").strftime("%Y-%m-%d")
    except (ValueError,TypeError):
        return ""

def aggregate_2026_approval_eligibility(approval_rows,quote_rows,cutoff=CUTOFF):
    if not isinstance(approval_rows,list) or not isinstance(quote_rows,list):
        raise ValueError("SOURCE_ROWS_INVALID")
    lookup=defaultdict(list)
    for line in quote_rows:
        if not isinstance(line,dict):raise ValueError("QQ_ROW_NOT_DICTIONARY")
        qid=line.get("SFDC Quotation ID","")
        if qid:lookup[qid].append(line)
    tally=Counter()
    months=Counter()
    seen=set()
    for row in approval_rows:
        if not isinstance(row,dict):raise ValueError("APPROVAL_ROW_NOT_DICTIONARY")
        qid=row.get("quotation_name","")
        if not QID.fullmatch(qid):continue
        day=row.get("quotation_created_date","")
        if not isinstance(day,str) or not (day.startswith("2026-") and day<cutoff):
            continue
        months[day[:7]]+=1
        if qid in seen:
            tally["DUPLICATE_APPROVAL"]+=1
            continue
        seen.add(qid)
        if not RECORD.fullmatch(row.get("salesforce_record_id","")) or not row.get("approved_at_kst") or not row.get("quotation_id"):
            tally["INVALID_APPROVAL_LINK"]+=1
            continue
        references=lookup.get(qid,[])
        if not references:
            tally["NO_MATCHING_QQ_LINES"]+=1
            continue
        if any(x.get("Active")!="1" for x in references):
            tally["INACTIVE"]+=1
            continue
        actual=source_date(references[0].get("Created Date"))
        if actual!=day or not qid.startswith("QID-"+day+"-") or any(source_date(x.get("Created Date"))!=actual for x in references):
            tally["CREATED_DATE_MISMATCH"]+=1
            continue
        if any(not x.get("Quotation Product ID") or not PROCESS.fullmatch(x.get("Process Name: SFDC Process ID","")) or not x.get("Quote Process Name") for x in references):
            tally["PROCESS_ID_MISSING"]+=1
            continue
        products={x.get("Quotation Product ID") for x in references}
        if len(products)>1:
            tally["MULTI_PRODUCT"]+=1
            continue
        mapping={}
        conflict=False
        for x in references:
            name=x["Quote Process Name"]
            pid=x["Process Name: SFDC Process ID"]
            if name in mapping and mapping[name]!=pid:conflict=True
            mapping[name]=pid
        if conflict:
            tally["PROCESS_ID_CONFLICT"]+=1
            continue
        tally["SINGLE_PRODUCT_ELIGIBLE"]+=1
    approved=sum(months.values())
    verified=sum(tally.values())
    if approved<1 or verified!=approved:
        raise ValueError("APPROVAL_COVERAGE_INCOMPLETE")
    return {"status":"PASS","scope":"APPROVED_QUOTES_BEFORE_2026_10_19",
            "cutoff_date_exclusive":cutoff,
            "approval_rows_2026":approved,"distinct_qids":len(seen),
            "eligibility_counts":dict(sorted(tally.items())),
            "monthly_approval_counts":dict(sorted(months.items())),
            "native_krw_process_price_available_in_qq":False,
            "price_auto_apply":False,"crm_writes":0}


def run_live():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    from oppo_quote_popular_patterns import (
        read_live_matrix,normalize_matrix,verify_mail_audit,
        OPP_TAB,QUOTE_TAB,AUDIT_TAB,EXPECTED_OPP,EXPECTED_QUOTE,EXPECTED_AUDIT
    )
    import os
    raw=os.getenv("GCP_SERVICE_ACCOUNT_JSON","")
    if not raw:raise ValueError("SOURCE_CREDENTIAL_UNAVAILABLE")
    cred=service_account.Credentials.from_service_account_info(json.loads(raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    sess=AuthorizedSession(cred)
    qq=normalize_matrix(read_live_matrix(sess,QUOTE_TAB,"A1:Y6000"),EXPECTED_QUOTE)
    opp=normalize_matrix(read_live_matrix(sess,OPP_TAB,"A1:O2000"),EXPECTED_OPP)
    audit=normalize_matrix(read_live_matrix(sess,AUDIT_TAB,"A1:J30"),EXPECTED_AUDIT)
    evidence=verify_mail_audit({"opportunities":opp,"quotation":qq},audit[2])
    approval=normalize_matrix(read_live_matrix(sess,"Quotation Approvals","A1:W1000"),APPROVAL_COLUMNS)
    result=aggregate_2026_approval_eligibility(approval[2],qq[2])
    result["source_integrity"]="PASS_HASH_VERIFIED"
    result["quote_source_received_kst"]=evidence["quotation"]["received_kst"]
    result["approval_source_kind"]="QUOTATION_APPROVAL_MAIL_TABLE"
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--audit-live",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if not args.audit_live:parser.error("Only --audit-live (aggregate QQ approval audit) is supported")
    try:
        summary=run_live()
    except Exception:
        summary={"status":"SOURCE_UNAVAILABLE","source_integrity":"SOURCE_UNAVAILABLE",
                 "crm_writes":0,"price_auto_apply":False}
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(summary,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    # Aggregates ONLY; never print customer source records or quotation IDs.
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    if summary["status"]!="PASS":raise SystemExit(2)


if __name__=="__main__":
    main()
