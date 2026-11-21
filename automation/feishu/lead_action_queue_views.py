#!/usr/bin/env python3
"""Isolated Feishu Lead action queues with a single automation-owned text field.

Manual checkboxes are NEVER written. A derived text field is synchronized from
their current values, then three views filter that known-good text field.
All source fields are read-only. Existing Feishu views and business tables are
never changed. Default mode is read-only; verified deployments update only the derived queue label.
"""
import argparse
import json
import sys
from collections import Counter

import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
import lead_eligibility as age
from lead_mail_views_sync import check_parity, get_one_view, filter_matches
from sales_home_links import API, BASE, pages, request, require_success

EXPECTED_TABLE_ID = manual.EXPECTED_TABLE_ID
QUEUE_FIELD = "Lead 업무 우선순위 (자동)"
ELIGIBILITY_FIELD = age.ELIGIBILITY_FIELD
QUEUE_LABELS = {
    "recontact": "01 · 재연락 필요",
    "planned": "02 · 메일 발송 예정",
    "review": "03 · 검토 대기",
    "none": "관리 제외 / 발송 확인",
    "expired": "04 · 1년 초과 · 연락 대상 제외",
}
QUEUES = (
    ("03 · 최우선 · 재연락 필요", "recontact"),
    ("04 · 메일 발송 예정", "planned"),
    ("05 · 검토 대기 · 메일 증거 없음", "review"),
)
NO_EVIDENCE = "메일 발송 증거 없음"

def classify(row, today=None):
    if age.eligibility(row, today) == "expired":
        return "expired"
    if manual.checked(row.get("재연락 필요")):
        return "recontact"
    if manual.checked(row.get("메일 발송 예정")):
        return "planned"
    status = lead.norm(row.get("Lead Status")).casefold()
    if any(s in status for s in ("converted", "qualified", "disqualified")):
        return "none"
    if (not manual.checked(row.get("검토 완료")) and
            lead.norm(row.get("연락 구분")) == NO_EVIDENCE):
        return "review"
    return "none"

def partition(records, today=None):
    today = today or age.today_kst()
    buckets = {name: set() for name in QUEUE_LABELS}
    for key, row in records.items():
        buckets[classify(row, today)].add(key)
    if sum(len(x) for x in buckets.values()) != len(records):
        raise RuntimeError("LEAD_QUEUE_PARTITION_INVALID")
    return buckets

def filter_definition(field_id, kind):
    if kind not in QUEUE_LABELS:
        raise RuntimeError("LEAD_QUEUE_KIND_INVALID")
    return {"conjunction":"and", "conditions":[
        {"field_id":field_id, "operator":"is",
         "value":json.dumps([QUEUE_LABELS[kind]],ensure_ascii=False)}
    ]}

def manual_snapshot(records):
    return {key:{field:manual.checked(row.get(field))
                 for field in manual.MANUAL}
            for key,row in records.items()}

def audit_snapshots(before, after, desired, source):
    if set(before) != set(after) or set(after) != set(desired):
        raise RuntimeError("LEAD_QUEUE_READBACK_ID_MISMATCH")
    check_parity(source, after)
    for key, value in desired.items():
        if lead.norm(after[key].get(QUEUE_FIELD)) != value:
            raise RuntimeError("LEAD_QUEUE_DERIVED_FIELD_READBACK_MISMATCH")
        if lead.norm(after[key].get(ELIGIBILITY_FIELD)) != age.label(before[key]):
            raise RuntimeError("LEAD_QUEUE_ELIGIBILITY_FIELD_READBACK_MISMATCH")
    old_checks = manual_snapshot(before)
    if old_checks != manual_snapshot(after):
        raise RuntimeError("LEAD_QUEUE_MANUAL_FLAGS_CHANGED")
    return len(after)

def load_records(root,token):
    records={}
    for rec in pages(root+"/records",token):
        row=rec.get("fields") or {}
        key=lead.norm(row.get("Lead ID"))
        if not key or key in records or not rec.get("record_id"):
            raise RuntimeError("LEAD_QUEUE_RECORD_ID_INVALID")
        records[key]={"record_id":rec["record_id"],"fields":row}
    return records

def read_view_ids(root,token,view_id):
    found=set()
    for rec in pages(root+"/records",token,{"view_id":view_id}):
        key=lead.norm((rec.get("fields") or {}).get("Lead ID"))
        if not key or key in found:
            raise RuntimeError("LEAD_QUEUE_VIEW_DUPLICATE_OR_EMPTY_ID")
        found.add(key)
    return found

def main(apply=False):
    source = lead.sheets_data()
    token = lead.auth()
    tables=[x for x in pages(API+"/tables",token) if x.get("name")==lead.TABLE]
    if len(tables)!=1 or tables[0].get("table_id")!=EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_QUEUE_WRONG_TABLE")
    root=API+"/tables/"+EXPECTED_TABLE_ID
    fields=list(pages(root+"/fields",token))
    matched=[x for x in fields if x.get("field_name")==QUEUE_FIELD]
    eligibility_matched=[x for x in fields if x.get("field_name")==ELIGIBILITY_FIELD]
    if (len(matched)>1 or (matched and matched[0].get("type")!=1)
            or len(eligibility_matched)>1
            or (eligibility_matched and eligibility_matched[0].get("type")!=1)):
        raise RuntimeError("LEAD_QUEUE_FIELD_SCHEMA_INVALID")
    for name in manual.MANUAL:
        matches=[x for x in fields if x.get("field_name")==name]
        if len(matches)!=1 or matches[0].get("type")!=7:
            raise RuntimeError("LEAD_QUEUE_MANUAL_SCHEMA_INVALID")
    old=load_records(root,token)
    old_fields={key:rec["fields"] for key,rec in old.items()}
    check_parity(source,old_fields)
    today=age.today_kst()
    desired={key:QUEUE_LABELS[classify(row,today)] for key,row in old_fields.items()}
    eligibility_values={key:age.label(row,today) for key,row in old_fields.items()}
    groups=partition(old_fields,today)
    updates=[]
    for key,rec in old.items():
        new_values={}
        if lead.norm(rec["fields"].get(QUEUE_FIELD))!=desired[key]:
            new_values[QUEUE_FIELD]=desired[key]
        if lead.norm(rec["fields"].get(ELIGIBILITY_FIELD))!=eligibility_values[key]:
            new_values[ELIGIBILITY_FIELD]=eligibility_values[key]
        if new_values:
            updates.append({"record_id":rec["record_id"],"fields":new_values})
    stats={k:len(v) for k,v in groups.items()}
    eligibility_stats=age.stats(old_fields.values(),today)
    print("LEAD_QUEUE_PLAN="+json.dumps({
        "total":len(old),"changes":len(updates),
        "queue_field_exists":bool(matched),"eligibility_field_exists":bool(eligibility_matched),
        "eligibility":eligibility_stats,"groups":stats,
        "mode":"APPLY" if apply else "READ_ONLY"
    },ensure_ascii=False),flush=True)

    if apply:
        if not matched:
            require_success(request("POST",root+"/fields",token=token,
                body={"field_name":QUEUE_FIELD,"type":1}),"CREATE_QUEUE_FIELD")
            current=[x for x in pages(root+"/fields",token)
                     if x.get("field_name")==QUEUE_FIELD]
            if len(current)!=1 or current[0].get("type")!=1:
                raise RuntimeError("LEAD_QUEUE_FIELD_CREATE_READBACK_FAILED")
            matched=current
        if not eligibility_matched:
            require_success(request("POST",root+"/fields",token=token,
                body={"field_name":ELIGIBILITY_FIELD,"type":1}),"CREATE_ELIGIBILITY_FIELD")
            eligibility_matched=[x for x in pages(root+"/fields",token)
                                 if x.get("field_name")==ELIGIBILITY_FIELD]
            if len(eligibility_matched)!=1 or eligibility_matched[0].get("type")!=1:
                raise RuntimeError("LEAD_ELIGIBILITY_FIELD_CREATE_READBACK_FAILED")
        for start in range(0,len(updates),100):
            require_success(request("POST",root+"/records/batch_update",token=token,
                body={"records":updates[start:start+100]}),"UPSERT_QUEUE_LABELS")
            print("LEAD_QUEUE_UPSERT_PROGRESS="+str(min(start+100,len(updates)))+
                  "/"+str(len(updates)),flush=True)
    if not matched or not eligibility_matched:
        print("LEAD_QUEUE_DRY_RUN_MISSING_FIELD=true",flush=True)
        return
    field_id=matched[0].get("field_id")
    if not eligibility_matched[0].get("field_id"):
        raise RuntimeError("LEAD_ELIGIBILITY_FIELD_ID_MISSING")
    if not field_id:
        raise RuntimeError("LEAD_QUEUE_FIELD_ID_MISSING")
    if apply:
        after_records=load_records(root,token)
        after={key:record["fields"] for key,record in after_records.items()}
        count=audit_snapshots(old_fields,after,desired,source)
        print("LEAD_QUEUE_MANUAL_STATES_PRESERVED="+str(count),flush=True)
    elif updates:
        print("LEAD_QUEUE_DRY_RUN_PENDING="+str(len(updates)),flush=True)
        return

    views=list(pages(root+"/views",token))
    for title,kind in QUEUES:
        matches=[x for x in views if x.get("view_name")==title]
        if len(matches)>1:
            raise RuntimeError("LEAD_QUEUE_DUPLICATE_VIEW_NAME")
        view_id=matches[0].get("view_id") if matches else None
        wanted=filter_definition(field_id,kind)
        if not view_id:
            if not apply:
                print("LEAD_QUEUE_VIEW_MISSING_DRY_RUN="+title,flush=True)
                continue
            data=require_success(request("POST",root+"/views",token=token,
                body={"view_name":title,"view_type":"grid"}),"CREATE_LEAD_QUEUE_VIEW")
            view_id=(data.get("view") or {}).get("view_id") or data.get("view_id")
            if not view_id:
                raise RuntimeError("LEAD_QUEUE_CREATE_VIEW_ID_MISSING")
        view=get_one_view(root,token,view_id)
        if view.get("view_name")!=title or view.get("view_type")!="grid":
            raise RuntimeError("LEAD_QUEUE_UNEXPECTED_VIEW")
        if not filter_matches((view.get("property") or {}).get("filter_info"),wanted):
            if not apply:
                print("LEAD_QUEUE_FILTER_PENDING="+title,flush=True)
                continue
            require_success(request("PATCH",root+"/views/"+view_id,token=token,
                body={"property":{"filter_info":wanted}}),"SET_QUEUE_TEXT_FILTER")
            view=get_one_view(root,token,view_id)
            if not filter_matches((view.get("property") or {}).get("filter_info"),wanted):
                raise RuntimeError("LEAD_QUEUE_FILTER_READBACK_FAILED")
        visible=read_view_ids(root,token,view_id)
        if visible!=groups[kind]:
            raise RuntimeError("LEAD_QUEUE_VISIBLE_RECORDS_MISMATCH_"+kind)
        print("LEAD_QUEUE_VIEW_VERIFIED="+json.dumps({
            "kind":kind,"count":len(visible),
            "url":f"https://ocnz4cb25scn.feishu.cn/base/{BASE}?table={EXPECTED_TABLE_ID}&view={view_id}"
        },ensure_ascii=False),flush=True)
    print("LEAD_QUEUE_READBACK_PASS=1 MODE="+
          ("APPLY" if apply else "READ_ONLY"),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    try:
        main(args.apply)
    except Exception as exc:
        print("LEAD_QUEUE_FAILED="+str(exc),file=sys.stderr)
        sys.exit(1)
