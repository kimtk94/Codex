#!/usr/bin/env python3
"""Supplement Quote-first project views with independently cross-checked historical USD.

No *current* Quote amount is created. Two derived Feishu operation tables only.
Source Project Progress Board, Google Sheets, SFDC and Revenue stay READ-ONLY.
'Historic USD reference' is explicitly dated and never treated as confirmed price.
"""
import argparse
import collections
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import os
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

from sales_home_links import API, PROJECT_BOARD, pages, request, require, extract_token, require_success
from project_quote_operating_sync import TABLES, all_tables, value
from project_quote_qid_money_audit import (
    TABS, read_rows, portfolio_index, quote_reference, header_index,
    price_evidence, text, verify_qq_process_report_audit
)

REF_FIELDS={
    "SFDC Quote QID":1,
    "과거 Quote 참고 금액 (K USD, VAT 제외)":2,
    "과거 Quote 금액 기준일":1,
    "과거 Quote 금액 상태":1,
}
ELIGIBLE_EVIDENCE="REFERENCE_ONLY_RATIO_NEAR_1_USD"
VERIFIED_STATUS="HISTORIC_REFERENCE_NOT_CURRENT"
KST=timezone(timedelta(hours=9))

def historical_fields(board, portfolio, headers, date):
    f=board.get("fields") or {}
    amea=text(f.get("AMEA")).upper()
    match,reason=quote_reference(board,portfolio.get(amea,[]))
    out={"과거 Quote 금액 상태":reason}
    if not match:
        return out
    out["SFDC Quote QID"]=match["qid"]
    proof,usd=price_evidence(match,headers)
    if proof==ELIGIBLE_EVIDENCE and usd is not None and usd>0:
        out["과거 Quote 참고 금액 (K USD, VAT 제외)"]=float(usd/Decimal(1000))
        out["과거 Quote 금액 기준일"]=date
        out["과거 Quote 금액 상태"]=VERIFIED_STATUS
    else:
        out["과거 Quote 금액 상태"]=proof
    return out

def historical_same(existing, wanted):
    for key,kind in REF_FIELDS.items():
        got=existing.get(key)
        expect=wanted.get(key)
        if kind==2:
            if expect is None:
                if got is not None and value(got)!="":return False
            else:
                try:
                    if abs(Decimal(value(got))-Decimal(str(expect)))>Decimal("0.0000001"):
                        return False
                except Exception:return False
        elif (value(got) if got is not None else "") != (value(expect) if expect is not None else ""):
            return False
    return True

def mutation(existing,wanted):
    changes={}
    for field,kind in REF_FIELDS.items():
        old=existing.get(field)
        new=wanted.get(field)
        if kind==2 and new is not None:
            try:
                if abs(Decimal(value(old))-Decimal(str(new)))<=Decimal("0.0000001"):
                    continue
            except Exception:pass
        elif (value(old) if old is not None else "") == (value(new) if new is not None else ""):
            continue
        changes[field]=new if new is not None else None
    return changes

def preflight(views, tables, expected_ids):
    """Fail before writes if source/derived membership or identity changed."""
    result={}
    for kind,records in views.items():
        tid=expected_ids[tables[kind][0]]
        found=set()
        for row in records:
            f=row.get("fields") or {}
            k=text(f.get("Source Key"))
            if not k or k in found:raise RuntimeError("SOURCE_VIEW_DUPLICATE_KEY")
            found.add(k)
        result[kind]=found
    if result["active"] & result["billing"]:
        raise RuntimeError("SOURCE_VIEW_LIFECYCLE_OVERLAP")
    return result

def supplement(token,kind,table_id,source_rows,index,headers,date,apply):
    root=API+"/tables/"+table_id
    rows=list(pages(root+"/records",token))
    matched={}
    for row in rows:
        f=row.get("fields") or {}
        key=text(f.get("Source Key"))
        if not key or key in matched:
            raise RuntimeError("DERIVED_DUPLICATE_OR_MISSING_SOURCE_KEY")
        matched[key]=row
    source={text((r.get("fields") or {}).get("Source Key")):r for r in source_rows}
    if set(matched)!=set(source):
        raise RuntimeError("DERIVED_SOURCE_SET_MISMATCH")
    changes=[]
    counters=collections.Counter()
    sample={}
    for key,row in source.items():
        target=historical_fields(row,index,headers,date)
        counters[target["과거 Quote 금액 상태"]]+=1
        sample[key]=target
        previous=matched[key]
        updated=mutation(previous.get("fields") or {},target)
        if updated:
            changes.append({"record_id":previous["record_id"],"fields":updated})
    print("HISTORIC_QUOTE_PLAN kind="+kind+" source_rows="+str(len(source))+
          " updates="+str(len(changes))+" states="+json.dumps(dict(counters),sort_keys=True),flush=True)
    if not apply:return dict(counters)
    for i in range(0,len(changes),100):
        require_success(request("POST",root+"/records/batch_update",token=token,
                body={"records":changes[i:i+100]}),"HISTORIC_QUOTE_WRITE")
    readback=list(pages(root+"/records",token))
    if len(readback)!=len(matched):raise RuntimeError("HISTORIC_QUOTE_READBACK_ROW_COUNT")
    result={}
    for row in readback:
        key=text((row.get("fields") or {}).get("Source Key"))
        if key in result or key not in sample:
            raise RuntimeError("HISTORIC_QUOTE_READBACK_KEY")
        result[key]=row.get("fields") or {}
    if set(result)!=set(sample) or not all(historical_same(result[k],sample[k]) for k in sample):
        raise RuntimeError("HISTORIC_QUOTE_READBACK_VALUE")
    print("HISTORIC_QUOTE_READBACK_PASS kind="+kind+
          " rows="+str(len(readback))+" historic_amount_rows="+str(counters[VERIFIED_STATUS]),flush=True)
    return dict(counters)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    if args.apply and os.getenv("FEISHU_HISTORIC_QUOTE_APPLY")!="1":
        raise RuntimeError("HISTORIC_QUOTE_WRITE_NOT_AUTHORIZED")
    creds=service_account.Credentials.from_service_account_info(
        json.loads(require("GCP_SERVICE_ACCOUNT_JSON")),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(creds)
    data={k:read_rows(session,*v) for k,v in TABS.items()}
    proof=verify_qq_process_report_audit(data["products"],data["audit"])
    dates={text(row.get("Exported At KST")) for row in data["headers"][0]
           if text(row.get("Exported At KST"))}
    if len(dates)!=1:raise RuntimeError("HISTORICAL_EXPORT_DATE_NOT_UNIQUE")
    date_stamp=next(iter(dates))
    date=datetime.strptime(date_stamp,"%Y-%m-%d %H:%M:%S KST").replace(tzinfo=KST)
    if date>datetime.now(KST)+timedelta(minutes=10):
        raise RuntimeError("HISTORICAL_EXPORT_DATE_IN_FUTURE")
    index=portfolio_index(data["portfolio"][0])
    headers=header_index(data["headers"][0])
    token=extract_token(request("POST","/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")}))
    master=API+"/tables/"+PROJECT_BOARD
    views={kind:list(pages(master+"/records",token,{"view_id":vid}))
            for kind,(_,vid) in TABLES.items()}
    ids=all_tables(token)
    if any(name not in ids for name,_ in TABLES.values()):
        raise RuntimeError("HISTORIC_PROJECT_DERIVED_TABLE_MISSING")
    preflight(views,TABLES,ids)
    for name,_ in TABLES.values():
        root=API+"/tables/"+ids[name]
        have={f.get("field_name"):f.get("type") for f in pages(root+"/fields",token)}
        mismatched=[field for field,t in REF_FIELDS.items() if field in have and have[field]!=t]
        if mismatched:raise RuntimeError("HISTORIC_FIELD_TYPE_MISMATCH")
    if args.apply:
        for name,_ in TABLES.values():
            root=API+"/tables/"+ids[name]
            have={f.get("field_name") for f in pages(root+"/fields",token)}
            for field,kind in REF_FIELDS.items():
                if field not in have:
                    require_success(request("POST",root+"/fields",token=token,
                        body={"field_name":field,"type":kind}),"HISTORIC_FIELD_CREATE")
    totals=collections.Counter()
    for kind,(name,_) in TABLES.items():
        counters=supplement(token,kind,ids[name],views[kind],index,headers,date.strftime("%Y-%m-%d"),args.apply)
        totals.update(counters)
    print("HISTORIC_QUOTE_RESULT "+json.dumps({
        "active_records":len(views["active"]),"billing_records":len(views["billing"]),
        "reference_amount_rows":totals[VERIFIED_STATUS],
        "export_date":date.strftime("%Y-%m-%d"),
        "current_quote_amount_verified":0,
        "source_received_kst":proof["received_kst"],
        "source_hash_verified":True,
        "original_project_writes":0,"actual_revenue_writes":0,
        "mode":"APPLY" if args.apply else "DRY_RUN"},sort_keys=True))
    print("HISTORIC_QUOTE_"+("SYNC_PASS" if args.apply else "AUDIT_PASS"),flush=True)
if __name__=="__main__":
    main()
