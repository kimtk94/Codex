#!/usr/bin/env python3
"""Feishu native weekly chart directly on user-editable Quote Review records.

The opt-out checkbox is a native Feishu field. Chart filtering happens inside
Base without waiting for GitHub Actions to recompute the weekly KPI table.
No source, checkbox or financial data is modified by this module.
"""
import collections
from decimal import Decimal, InvalidOperation
import re

from qq_mail_ingest import SafeError, auth, list_all, plain_field
from weekly_quote_review import checkbox

BASE_NAME="IpMkbUD0vaFqtYs93a3csXtdn1b"
SOURCE_TABLE="Weekly Quote Review"
SUMMARY_TABLE="Weekly Quote KPI"
COUNT_FIELD="실시간 집계용 건수"
AMOUNT_FIELD="참고 금액 K USD"
WINDOW="RECENT_4_PLUS_CURRENT"
INCLUDED_FILTERS=(
    ("Chart Window","RECENT_4_PLUS_CURRENT"),
    ("Quote Status","ACTIVE"),
    ("Approved AND Active","YES"),
    ("SFDC IsActive","1"),
)
CHECKBOX_FIELD="합산 제외"

def config():
    """Two native SUM series avoid unsupported count_all+series combination."""
    return {
        "table_name":SOURCE_TABLE,
        "series":[{"field_name":COUNT_FIELD,"rollup":"SUM"},
                  {"field_name":AMOUNT_FIELD,"rollup":"SUM"}],
        "group_by":[{"field_name":"Week Start","mode":"integrated",
                     "sort":{"type":"group","order":"asc"}}],
        "filter":{"conjunction":"and","conditions":[
            *[{"field_name":field,"operator":"is","value":expected}
              for field,expected in INCLUDED_FILTERS],
            {"field_name":CHECKBOX_FIELD,"operator":"is","value":False},
        ]},
    }

def plain(x):
    return plain_field(x).strip() if x is not None else ""

def dec(x):
    v=plain(x)
    if not v:return None
    try:
        d=Decimal(v.replace(",",""))
    except InvalidOperation:
        raise SafeError("LIVE_QUOTE_INVALID_NUMERIC_SOURCE") from None
    if not d.is_finite() or d<0:
        raise SafeError("LIVE_QUOTE_INVALID_NUMERIC_SOURCE")
    return d

def matches_live(row):
    """Never read lagged '합산 상태'; the checkbox is authoritative now."""
    return all(plain(row.get(field))==desired for field,desired in INCLUDED_FILTERS) and not checkbox(
        row.get(CHECKBOX_FIELD))

def audit_rows(review_records,kpi_records):
    keys=set()
    weeks=collections.defaultdict(lambda:{"count":0,"usd":Decimal(0),"no_amount":0})
    window_weeks=set()
    for rec in review_records:
        fields=rec.get("fields") or {}
        key=plain(fields.get("Source Key"))
        if not key.startswith("QUOTE_REVIEW:a0P") or key in keys:
            raise SafeError("LIVE_QUOTE_SOURCE_KEY_INVALID_OR_DUPLICATE")
        keys.add(key)
        unit=dec(fields.get(COUNT_FIELD))
        if unit!=1:
            raise SafeError("LIVE_QUOTE_COUNT_UNIT_NOT_BACKFILLED")
        if plain(fields.get("Chart Window"))==WINDOW:
            week=plain(fields.get("Week Start"))
            if not re.fullmatch(r"20\d\d-\d\d-\d\d",week):
                raise SafeError("LIVE_QUOTE_MISSING_WEEK")
            window_weeks.add(week)
            if matches_live(fields):
                weeks[week]["count"]+=1
                amount=dec(fields.get(AMOUNT_FIELD))
                if amount is None:
                    weeks[week]["no_amount"]+=1
                else:
                    weeks[week]["usd"]+=amount
    if len(review_records)<100:
        raise SafeError("LIVE_QUOTE_SOURCE_INCOMPLETE")
    summaries={}
    for rec in kpi_records:
        f=rec.get("fields") or {}
        if plain(f.get("Chart Window"))!=WINDOW:
            continue
        week=plain(f.get("Week Start"))
        if week in summaries:
            raise SafeError("LIVE_QUOTE_WEEK_DUPLICATE")
        summaries[week]=f
    if len(summaries)!=5:
        raise SafeError("LIVE_QUOTE_EXPECT_FIVE_WEEKS")
    if not window_weeks.issubset(summaries):
        raise SafeError("LIVE_QUOTE_REVIEW_WINDOW_NOT_IN_KPI")
    for week,f in summaries.items():
        value=dec(f.get("Included Quote Count"))
        if value is None:
            raise SafeError("LIVE_QUOTE_KPI_INCLUDED_COUNT_WITHHELD")
        observed=weeks[week]["count"]
        if value!=Decimal(observed):
            raise SafeError("LIVE_QUOTE_INCLUDED_COUNT_PARITY_FAILED")
        known=dec(f.get("Calculated Quote Value K USD"))
        if weeks[week]["no_amount"]>0:
            # A missing amount may not be shown to users as a genuine zero.
            raise SafeError("LIVE_QUOTE_UNVERIFIED_INCLUDED_AMOUNT")
        if observed>0 and known is None:
            raise SafeError("LIVE_QUOTE_KPI_MONEY_WITHHELD")
        # Source row K USD is rounded at 4 decimal places per Quote.
        if known is not None and abs(known-weeks[week]["usd"])>Decimal("0.01"):
            raise SafeError("LIVE_QUOTE_AMOUNT_PARITY_FAILED")
    return {
        "total_quote_rows":len(review_records),
        "chart_window_quote_rows":sum(
            plain((r.get("fields") or {}).get("Chart Window"))==WINDOW
            for r in review_records),
        "week_count":len(summaries),
        "included_quote_count":sum(v["count"] for v in weeks.values()),
        "checkbox_filters":1,
        "amount_withheld_cases":sum(v["no_amount"] for v in weeks.values()),
        "source_writes":0,
    }

def preflight():
    from sales_native_home import table_map, target_path
    token,root=auth()
    tables=table_map(token,root)
    if SOURCE_TABLE not in tables or SUMMARY_TABLE not in tables:
        raise SafeError("LIVE_QUOTE_TABLES_NOT_FOUND")
    review_path=target_path(root,tables[SOURCE_TABLE])
    fields=list_all(review_path+"/fields",token,"live_quote_field_types")
    types={r.get("field_name"):r.get("type") for r in fields}
    required={
        COUNT_FIELD:2,AMOUNT_FIELD:2,
        CHECKBOX_FIELD:7,"Week Start":1,"Chart Window":1,
        "SFDC IsActive":1,"Quote Status":1,"Approved AND Active":1,
    }
    if any(types.get(k)!=v for k,v in required.items()):
        raise SafeError("LIVE_QUOTE_SOURCE_SCHEMA_NOT_READY")
    review=list_all(review_path+"/records",token,"live_quote_review_source")
    summary=list_all(target_path(root,tables[SUMMARY_TABLE])+"/records",token,
                     "live_quote_weekly_kpi")
    out=audit_rows(review,summary)
    print("WEEKLY_LIVE_CHART_PREFLIGHT_PASS "+
          " ".join(str(k)+"="+str(v) for k,v in out.items()),flush=True)
    return out
