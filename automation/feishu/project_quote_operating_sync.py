#!/usr/bin/env python3
"""Materialize two Quote-first Feishu project operation tables from existing views.

The original Project Progress Board is READ ONLY. This never infers Quote value
from unverified SFDC product lines. No actual revenue is calculated here.
Use --apply (and FEISHU_PROJECT_OPS_APPLY=1) to write ONLY derived tables.
"""
import argparse
import collections
import datetime as dt
from decimal import Decimal, InvalidOperation
import os
import urllib.parse

from sales_home_links import API, PROJECT_BOARD, pages, request, extract_token, require, require_success

TABLES = {
    "active": ("프로젝트 운영 · 진행 중 (Quote)", "vew9v3YnBX"),
    "billing": ("프로젝트 운영 · 완료·결제 (Quote)", "vewzKSaZ1p"),
}
PAID_VIEW = "vewIKJf0Fj"
FIELDS = [
    ("Quote Name", 1), ("기관", 1), ("고객 Contact", 1),
    ("서비스", 1), ("현재 공정", 1), ("진행률 (%)", 2),
    ("진행률 바", 1), ("Quote 금액 (K USD)", 2),
    ("견적 금액 검증", 1), ("Invoice 조회액 (M KRW, VAT 포함)", 2),
    ("미수금 조회액 (M KRW)", 2), ("결제 상태", 1),
    ("다음 조치", 1), ("공정 증거", 1), ("최종 동기화 KST", 1),
    ("AMEA", 1), ("Source Key", 1), ("SFDC Quote Match State", 1),
    ("원본 프로젝트", 15)
]
RAW_VIEW = "https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=" + PROJECT_BOARD

def value(x):
    if x is None: return ""
    if isinstance(x, str): return x.strip()
    if isinstance(x, list): return " ".join(value(v) for v in x).strip()
    if isinstance(x, dict):
        return str(x.get("text") or x.get("value") or x.get("name") or "").strip()
    return str(x).strip()

def number(x, minimum=None, maximum=None):
    raw=value(x)
    if raw in ("", "—", "-", "no value", "N/A"):return None
    try:
        dec=Decimal(raw.replace(",", "").replace("₩", "").replace("$", ""))
    except (InvalidOperation,TypeError):
        raise RuntimeError("INVALID_NUMERIC_SOURCE")
    if not dec.is_finite() or (minimum is not None and dec<minimum) or (maximum is not None and dec>maximum):
        raise RuntimeError("SOURCE_AMOUNT_OUT_OF_RANGE")
    return float(dec)

def source_row(record):
    fields=record.get("fields") or {}
    quote=value(fields.get("Quote Full Name"))
    key=value(fields.get("Source Key"))
    if not quote or not key or len(quote)>10000:raise RuntimeError("SOURCE_IDENTIFIERS_MISSING")
    p=number(fields.get("Progress %"),0,100)
    invoice=number(fields.get("Invoice Gross M KRW"),0)
    outstanding=number(fields.get("Outstanding Balance M KRW"),0)
    row={
       "Quote Name":quote,
       "기관":value(fields.get("Institution")),
       "고객 Contact":value(fields.get("Customer")),
       "서비스":value(fields.get("Service")),
       "현재 공정":value(fields.get("Current Stage")),
       "진행률 바":value(fields.get("Progress Bar")),
       "견적 금액 검증":"UNVERIFIED: SFDC Quote ID/price source not jointly confirmed",
       "결제 상태":value(fields.get("Payment State")),
       "다음 조치":value(fields.get("Next Action")),
       "공정 증거":value(fields.get("Evidence")),
       "최종 동기화 KST":value(fields.get("Last Sync KST")),
       "AMEA":value(fields.get("AMEA")),
       "Source Key":key,
       "SFDC Quote Match State":value(fields.get("Quote Match State")),
       "원본 프로젝트":{"text":"원본","link":RAW_VIEW},
    }
    # Absence is blank, never zero. USD quote values intentionally remain blank.
    if p is not None:row["진행률 (%)"]=p
    if invoice is not None:row["Invoice 조회액 (M KRW, VAT 포함)"]=invoice
    if outstanding is not None:row["미수금 조회액 (M KRW)"]=outstanding
    return row

def validate_sources(original,views):
    allkeys=[value((r.get("fields") or {}).get("Source Key")) for r in original]
    if len(original)<100 or len(set(allkeys))!=len(original) or any(not k for k in allkeys):
        raise RuntimeError("BASE_SOURCE_KEY_INTEGRITY")
    sets={}
    for kind,records in views.items():
        entries={}
        names=set()
        for rec in records:
            f=rec.get("fields") or {}
            key=value(f.get("Source Key"))
            name=value(f.get("Quote Full Name"))
            if key not in set(allkeys) or key in entries or not name or name in names:
                raise RuntimeError("VIEW_IDENTIFIERS_NOT_UNIQUE")
            names.add(name)
            entries[key]=source_row(rec)
        sets[kind]=entries
    if not (1<=len(sets["active"])<=len(original) and 1<=len(sets["billing"])<=len(original)):
        raise RuntimeError("VIEW_SOURCE_EMPTY")
    if set(sets["active"]) & set(sets["billing"]):
        raise RuntimeError("VIEW_LIFECYCLE_OVERLAP")
    return sets

def schema_fields():
    return [{"field_name":k,"type":t} for k,t in FIELDS]

def all_tables(token):
    return {row.get("name"):row.get("table_id") for row in pages(API+"/tables",token)}

def ensure_table(token,available,name,apply):
    tid=available.get(name)
    if not tid and apply:
        ans=require_success(request("POST",API+"/tables",token=token,body={
           "table":{"name":name,"default_view_name":"Quote별 현황","fields":schema_fields()}
        }),"CREATE_TABLE")
        tid=ans.get("table_id") or (ans.get("table") or {}).get("table_id")
        if not tid:raise RuntimeError("CREATED_TABLE_ID_MISSING")
        print("DERIVED_TABLE_CREATED "+name,flush=True)
    if not tid:return None
    root=API+"/tables/"+tid
    exists={f.get("field_name"):f.get("type") for f in pages(root+"/fields",token)}
    required={k:t for k,t in FIELDS}
    if any(exists.get(k)!=t for k,t in required.items()):
        raise RuntimeError("DERIVED_SCHEMA_CHANGED")
    return tid

def equal_row(old,new):
    for k,expected in new.items():
        actual=old.get(k)
        if isinstance(expected,dict):
            if not isinstance(actual,dict) or actual.get("link")!=expected.get("link"):
                return False
        elif isinstance(expected,float):
            try:
                if Decimal(value(actual)) != Decimal(str(expected)):return False
            except InvalidOperation:return False
        elif value(actual)!=str(expected):
            return False
    # Previously populated amounts never survive if source becomes unavailable.
    for k in ("진행률 (%)","Invoice 조회액 (M KRW, VAT 포함)","미수금 조회액 (M KRW)","Quote 금액 (K USD)"):
        if k not in new and value(old.get(k)):
            return False
    return True

def batch(token,endpoint,records,chunk_size=100):
    for i in range(0,len(records),chunk_size):
        require_success(request("POST",endpoint,token=token,body={"records":records[i:i+chunk_size]}),"BATCH_WRITE")

def apply_table(token,table_id,desired,apply):
    root=API+"/tables/"+table_id
    original=list(pages(root+"/records",token))
    existing={}
    for rec in original:
        key=value((rec.get("fields") or {}).get("Source Key"))
        if not key or key in existing:raise RuntimeError("DERIVED_KEY_INTEGRITY")
        existing[key]=rec
    create=[];update=[]
    for key,fields in sorted(desired.items()):
        prev=existing.get(key)
        if prev is None:
            create.append({"fields":fields})
        elif not equal_row(prev.get("fields") or {},fields):
            updates=dict(fields)
            # Revoke stale Quote amounts; this dashboard cannot assert those values.
            for k in ("진행률 (%)","Invoice 조회액 (M KRW, VAT 포함)","미수금 조회액 (M KRW)","Quote 금액 (K USD)"):
                if k not in fields and value((prev.get("fields") or {}).get(k)):
                    updates[k]=None
            update.append({"record_id":prev["record_id"],"fields":updates})
    obsolete=[r["record_id"] for k,r in existing.items() if k not in desired]
    if len(obsolete)>max(5,len(existing)//4):
        raise RuntimeError("DERIVED_STALE_REMOVAL_TOO_LARGE")
    print("PROJECT_QUOTE_SYNC_PLAN "+str({"desired":len(desired),"existing":len(existing),
          "create":len(create),"update":len(update),"remove_derived_only":len(obsolete)}),flush=True)
    if not apply:return
    if create:batch(token,root+"/records/batch_create",create)
    if update:batch(token,root+"/records/batch_update",update)
    if obsolete:
        # Derived-only rows can be removed after full original-view integrity check.
        batch(token,root+"/records/batch_delete",obsolete)
    latest=list(pages(root+"/records",token))
    actual={}
    for rec in latest:
        f=rec.get("fields") or {}
        k=value(f.get("Source Key"))
        if not k or k in actual:raise RuntimeError("DERIVED_READBACK_DUPLICATE")
        actual[k]=f
    if set(actual)!=set(desired):
        raise RuntimeError("DERIVED_READBACK_SET_MISMATCH")
    if any(not equal_row(actual[k],v) for k,v in desired.items()):
        raise RuntimeError("DERIVED_READBACK_VALUE_MISMATCH")
    print("PROJECT_QUOTE_SYNC_VERIFIED rows="+str(len(actual)),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    if args.apply and os.environ.get("FEISHU_PROJECT_OPS_APPLY")!="1":
        raise RuntimeError("WRITE_NOT_AUTHORIZED")
    token=extract_token(request("POST","/open-apis/auth/v3/tenant_access_token/internal",
               body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")}))
    base=API+"/tables/"+PROJECT_BOARD
    original=list(pages(base+"/records",token))
    views={kind:list(pages(base+"/records",token,{"view_id":vid}))
           for kind,(_,vid) in TABLES.items()}
    archived=list(pages(base+"/records",token,{"view_id":PAID_VIEW}))
    desired=validate_sources(original,views)
    overlap=set(desired["active"])&{value((r.get("fields") or {}).get("Source Key")) for r in archived}
    if overlap:raise RuntimeError("PAID_PROJECT_STILL_ACTIVE")
    print("SOURCE_CHECK total="+str(len(original))+" active="+str(len(desired["active"]))+
          " billing="+str(len(desired["billing"]))+" archived="+str(len(archived))+
          " unclassified="+str(len(original)-len(set(desired["active"])|set(desired["billing"])|
               {value((r.get("fields") or {}).get("Source Key")) for r in archived}))+
          " quote_amount_verified=0",flush=True)
    tables=all_tables(token)
    for kind,(name,_) in TABLES.items():
        target=ensure_table(token,tables,name,args.apply)
        if target:
            apply_table(token,target,desired[kind],args.apply)
        else:
            print("DERIVED_TABLE_PENDING name="+name+" expected_rows="+str(len(desired[kind])),flush=True)
    print("PROJECT_QUOTE_SNAPSHOT_"+("PASS" if args.apply else "DRY_RUN_PASS"),flush=True)

if __name__=="__main__":main()
