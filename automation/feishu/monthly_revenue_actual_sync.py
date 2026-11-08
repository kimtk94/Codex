#!/usr/bin/env python3
"""Sync only audited monthly actuals into Feishu while SFDC reports are stale.

The original full KPI freshness guard is intentionally NOT bypassed: that guard
still protects all quote/project writes. This isolated workflow can only write
already reconciled official issued-invoice Revenue rows in Monthly Tax Invoice.
"""
import os
import sys
import re

from qq_mail_ingest import SafeError,auth,list_all
from monthly_revenue_canonical import evidence_rows,RevenueEvidenceError
from sales_metrics_sync import (EXPECTED_BASE,UNIFIED_SHEET,SCHEMAS,req_sheet,
                                sheets_session,table_catalog,table_path,
                                raw_value,equivalent,sync_table)


def read_canonical_sources():
    session=sheets_session()
    tabs=[
        ("BI Revenue Net VAT Monthly",120),
        ("BI Revenue Lifecycle Monthly",120),
        ("Revenue Source Authority",250),
    ]
    source={}
    for title,limit in tabs:
        source[title]=req_sheet(session,UNIFIED_SHEET,title,limit)
    try:
        rows=evidence_rows(source)
    except RevenueEvidenceError as exc:
        raise SafeError("MONTHLY_AUTHORITY_FAIL_CLOSED:"+str(exc)) from exc
    if len(rows)>24:
        raise SafeError("MONTHLY_CANONICAL_UNEXPECTED_SCOPE")
    print("MONTHLY_AUTHORITY_PASS months="+str(len(rows))+
          " month_range="+rows[-1]["Month"]+".."+rows[0]["Month"]+
          " net_basis=VAT_EXCLUDED pending_and_forecast=EXCLUDED",flush=True)
    return rows


def index_records(records):
    index={}
    for row in records:
        fields=row.get("fields") or {}
        key=raw_value(fields.get("Source Key")).strip()
        if not key:continue
        if key in index or not row.get("record_id"):
            raise SafeError("MONTHLY_DUPLICATE_OR_MISSING_RECORD_ID")
        index[key]=row
    return index


def validate_mail_only_existing(records):
    """Never let an ERP/eTax/Forecast source row enter the monthly chart."""
    seen=set()
    for record in records:
        fields=record.get("fields") or {}
        key=raw_value(fields.get("Source Key")).strip()
        if not re.fullmatch(r"INVOICE:20\d{2}-(?:0[1-9]|1[0-2])",key):
            raise SafeError("MONTHLY_NON_MAIL_SOURCE_RECORD_PRESENT")
        if key in seen:raise SafeError("MONTHLY_DUPLICATE_MAIL_SOURCE_MONTH")
        seen.add(key)
    print("MONTHLY_MAIL_ONLY_SOURCE_GUARD_PASS rows="+str(len(records))+
          " source_keys=INVOICE_MONTH_ONLY"+
          " manual_ERP_eTax_pending_forecast=EXCLUDED",flush=True)


def safe_existing_fields(record):
    return {k:raw_value(v).strip() for k,v in
            (record.get("fields") or {}).items() if k!="Last Sync KST"}


def verify_monthly_readback(before,after,desired):
    validate_mail_only_existing(before)
    validate_mail_only_existing(after)
    a=index_records(before)
    b=index_records(after)
    if not set(a).issubset(b):
        raise SafeError("MONTHLY_UNEXPECTED_RECORD_REMOVAL")
    desired_keys={row["Source Key"] for row in desired}
    if len(desired_keys)!=len(desired):
        raise SafeError("MONTHLY_DUPLICATE_DESIRED_KEY")
    for key in set(a)-desired_keys:
        if safe_existing_fields(a[key])!=safe_existing_fields(b[key]):
            raise SafeError("MONTHLY_UNRELATED_RECORD_CHANGED")
    for row in desired:
        if row["Source Key"] not in b or not equivalent(
                b[row["Source Key"]]["fields"],row):
            raise SafeError("MONTHLY_CANONICAL_READBACK_MISMATCH")
    print("MONTHLY_CANONICAL_READBACK_PASS checked="+str(len(desired))+
          " existing_other_months_preserved="+str(len(set(a)-desired_keys))+
          " pending_forecast_writes=0",flush=True)


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("MONTHLY_REFUSE_UNKNOWN_BASE")
    mode=os.environ.get("FEISHU_METRIC_MODE","plan")
    if mode not in ("plan","apply"):
        raise SafeError("MONTHLY_BAD_MODE")
    desired=read_canonical_sources()  # all source evidence before any writes
    token,root=auth()
    catalog=table_catalog(token,root)
    ids=catalog.get("Monthly Tax Invoice") or []
    if len(ids)!=1:raise SafeError("MONTHLY_TARGET_TABLE_NOT_UNIQUE")
    path=table_path(root,ids[0])
    existing_fields={x.get("field_name"):x.get("type")
                     for x in list_all(path+"/fields",token,"monthly_schema")}
    if any(existing_fields.get(name)!=kind
           for name,kind in SCHEMAS["Monthly Tax Invoice"]):
        raise SafeError("MONTHLY_TARGET_SCHEMA_UNVERIFIED")
    before=list_all(path+"/records",token,"monthly_existing")
    validate_mail_only_existing(before)
    index_records(before)
    print("MONTHLY_CANONICAL_PLAN source_months="+str(len(desired))+
          " existing_target_rows="+str(len(before))+" mode="+mode,flush=True)
    if mode=="plan":
        return
    created,updated,unchanged=sync_table(token,path,desired,limit=24)
    if created+updated+unchanged!=len(desired):
        raise SafeError("MONTHLY_SYNC_BOUNDED_PARTIAL")
    after=list_all(path+"/records",token,"monthly_readback")
    verify_monthly_readback(before,after,desired)
    print("MONTHLY_CANONICAL_APPLY_PASS created="+str(created)+
          " updated="+str(updated)+" unchanged="+str(unchanged)+
          " target=Monthly_Tax_Invoice other_tables_written=0",flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        reason=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("MONTHLY_CANONICAL_FAILED:"+reason,file=sys.stderr)
        sys.exit(1)
