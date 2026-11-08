#!/usr/bin/env python3
"""Idempotent Feishu weekly Quote *label-only* chronology migration.

This uses the already materialized Feishu Week Start and does not read or
calculate Salesforce data. A stale report must still block metric changes.
The only permitted write field is 'Chart Week Label'.
"""
import datetime as dt
import os
import re
import sys
import urllib.parse

from qq_mail_ingest import SafeError, api, auth, list_all

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
TABLE="Weekly Quote KPI"
LABEL_FIELD="Chart Week Label"
MIN_ESTABLISHED_WEEKS=95
MAX_CHANGES=200


def raw(value):
    if isinstance(value,str):return value
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,list):return "".join(raw(x) for x in value)
    if isinstance(value,dict):return raw(value.get("text") or value.get("value") or "")
    return ""


def week_display_label(week_start):
    """Same Friday->Monday boundary as canonical SFDC weekly KPI."""
    try:
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",week_start):
            return ""
        start=dt.date.fromisoformat(week_start)
        monday=start+dt.timedelta(days=3)
        if monday.weekday()!=0:return ""
        return monday.strftime("%b")+" W"+str((monday.day-1)//7+1)
    except ValueError:
        return ""


def parse_rows(records):
    """Fail on a bad key or date; do not silently skip rows or infer counts."""
    indexed={}
    for rec in records:
        fields=rec.get("fields") or {}
        key=raw(fields.get("Source Key")).strip()
        rid=rec.get("record_id")
        if not key.startswith("QUOTE:") or not isinstance(rid,str) or not rid:
            raise SafeError("QUOTE_LABEL_INVALID_KEY_OR_RECORD_ID")
        if key in indexed:raise SafeError("QUOTE_LABEL_DUPLICATE_SOURCE_KEY")
        week=raw(fields.get("Week Start")).strip()
        if key!="QUOTE:"+week or not week_display_label(week):
            raise SafeError("QUOTE_LABEL_WEEK_START_KEY_MISMATCH")
        indexed[key]=rec
    return indexed


def desired_labels(index):
    if not index:raise SafeError("QUOTE_LABEL_SOURCE_EMPTY")
    ongoing=sorted((raw(rec["fields"].get("Week Start")).strip()
                    for rec in index.values()
                    if "IN_PROGRESS" in raw(rec["fields"].get("Week Status")).upper()),
                   reverse=True)
    current=ongoing[0] if ongoing else None
    result={}
    for key,rec in index.items():
        week=raw(rec["fields"].get("Week Start")).strip()
        label=week+" · "+week_display_label(week)
        if week==current:label+=" · 진행 중"
        result[key]=label
    return result


def numerical_evidence(fields):
    """Exclude only the label; all existing evidence must be preserved."""
    return {name:raw(value) for name,value in fields.items()
            if name!=LABEL_FIELD}


def sync_labels(token,table_path,mode):
    before=parse_rows(list_all(table_path+"/records",token,"quote_label_before"))
    if len(before)<MIN_ESTABLISHED_WEEKS:
        raise SafeError("QUOTE_LABEL_HISTORICAL_COVERAGE_INCOMPLETE")
    desired=desired_labels(before)
    changes=[]
    for key in sorted(desired):
        rec=before[key]
        if raw(rec["fields"].get(LABEL_FIELD)).strip()!=desired[key]:
            changes.append({"record_id":rec["record_id"],
                            "fields":{LABEL_FIELD:desired[key]}})
    if len(changes)>MAX_CHANGES:raise SafeError("QUOTE_LABEL_WRITE_LIMIT")
    recent_weeks=sorted(raw(before[key]["fields"].get("Week Start"))
                        for key in desired if
                        raw(before[key]["fields"].get("Chart Window"))=="RECENT_4_PLUS_CURRENT")
    if len(recent_weeks)!=5 or len(set(recent_weeks))!=5:
        raise SafeError("QUOTE_LABEL_CHART_WINDOW_NOT_FIVE_WEEKS")
    chronological=[desired["QUOTE:"+week] for week in recent_weeks]
    if chronological!=sorted(chronological) or not all(
            re.match(r"20\d{2}-\d{2}-\d{2} · ",v) for v in chronological):
        raise SafeError("QUOTE_LABEL_CHRONOLOGY_INVALID")
    recent=chronological
    print("FEISHU_QUOTE_LABEL_PLAN weeks="+str(len(before))+
          " chart_weeks="+str(len(recent))+
          " changes="+str(len(changes))+" mode="+mode,flush=True)
    if mode=="plan":
        return len(changes)
    for i in range(0,len(changes),25):
        chunk=changes[i:i+25]
        response=api("POST",table_path+"/records/batch_update",token,
                     data={"records":chunk},action="quote_label_batch_update")
        if len(response.get("records") or [])!=len(chunk):
            raise SafeError("QUOTE_LABEL_BATCH_WRITE_UNVERIFIED")
    # Read after every apply, including no-op, so we verify all 95+ rows.
    after=parse_rows(list_all(table_path+"/records",token,"quote_label_readback"))
    if set(before)!=set(after):
        raise SafeError("QUOTE_LABEL_ROW_COVERAGE_CHANGED")
    for key in before:
        if raw(after[key]["fields"].get(LABEL_FIELD)).strip()!=desired[key]:
            raise SafeError("QUOTE_LABEL_READBACK_MISMATCH")
        if numerical_evidence(before[key]["fields"])!=numerical_evidence(after[key]["fields"]):
            raise SafeError("QUOTE_LABEL_NON_LABEL_FIELD_CHANGED")
    print("FEISHU_QUOTE_LABEL_PASS weeks="+str(len(after))+
          " changed="+str(len(changes))+
          " verified="+str(len(after))+
          " numeric_or_customer_fields_written=0",flush=True)
    return len(changes)


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise SafeError("QUOTE_LABEL_WRONG_BASE")
    mode=os.environ.get("FEISHU_DASHBOARD_MODE","plan")
    if mode not in {"plan","apply"}:
        raise SafeError("QUOTE_LABEL_INVALID_MODE")
    token,root=auth()
    tables=list_all(root+"/tables",token,"quote_label_table_catalog")
    matches=[t for t in tables if t.get("name")==TABLE]
    if len(matches)!=1 or not matches[0].get("table_id"):
        raise SafeError("QUOTE_LABEL_TABLE_UNRESOLVED")
    table_path=root+"/tables/"+urllib.parse.quote(matches[0]["table_id"],safe="")
    sync_labels(token,table_path,mode)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("FEISHU_QUOTE_LABEL_FAILED="+type(exc).__name__+
              ":"+(str(exc) if isinstance(exc,SafeError) else "UNEXPECTED"),
              file=sys.stderr)
        sys.exit(1)
