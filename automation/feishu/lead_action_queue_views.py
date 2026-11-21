#!/usr/bin/env python3
"""Three Feishu Lead operational views; audit/modify only view filters.

This consumer does not change Lead records, source mail, SFDC, Account or
existing views. User-managed checkboxes are read, never written.
Default mode is audit only. CI deployment validates and applies only the three managed views.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter

import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
from lead_mail_views_sync import check_parity, get_one_view
from sales_home_links import API, BASE, pages, request, require_success

EXPECTED_TABLE_ID = manual.EXPECTED_TABLE_ID
NO_EVIDENCE = "메일 발송 증거 없음"
# Display order defines precedence. Each view is disjoint by design.
QUEUES = (
    ("03 · 최우선 · 재연락 필요", "recontact"),
    ("04 · 메일 발송 예정", "planned"),
    ("05 · 검토 대기 · 메일 증거 없음", "review"),
)
REQUIRED = {
    "재연락 필요": 7,
    "메일 발송 예정": 7,
    "검토 완료": 7,
    "연락 구분": 1,
}
TRUE = "1"  # Bitable checkbox view filters use the numeric checked token

def condition(field_id, op, val):
    return {"field_id": field_id, "operator": op,
            "value": json.dumps([val], ensure_ascii=False)}

def queue_filter(field_ids, kind):
    # Feishu bitable/v1 view-filter syntax: values are JSON-encoded arrays.
    true = lambda f: condition(field_ids[f], "is", TRUE)
    false = lambda f: condition(field_ids[f], "isNot", TRUE)
    if kind == "recontact":
        conditions = [true("재연락 필요")]
    elif kind == "planned":
        conditions = [false("재연락 필요"), true("메일 발송 예정")]
    elif kind == "review":
        conditions = [false("재연락 필요"), false("메일 발송 예정"),
                      false("검토 완료"), condition(field_ids["연락 구분"],
                                                   "is", NO_EVIDENCE)]
    else:
        raise RuntimeError("UNKNOWN_QUEUE_KIND")
    return {"conjunction": "and", "conditions": conditions}

def conditions_equal(observed, expected):
    if not isinstance(observed, dict) or observed.get("conjunction") != "and":
        return False
    def normalize(value):
        result = []
        for cond in value.get("conditions") or []:
            raw = cond.get("value")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError):
                return None
            if not isinstance(parsed, list) or len(parsed) != 1:
                return None
            result.append((cond.get("field_id"), cond.get("operator"), str(parsed[0]).lower()))
        return sorted(result)
    return normalize(observed) == normalize(expected)

def classify(row):
    # Highest priority wins when multiple checkboxes are set.
    if manual.checked(row.get("재연락 필요")):
        return "recontact"
    if manual.checked(row.get("메일 발송 예정")):
        return "planned"
    if (not manual.checked(row.get("검토 완료")) and
            row.get("연락 구분") == NO_EVIDENCE):
        return "review"
    return "none"

def assert_queue_partition(records):
    output = {name: set() for _, name in QUEUES}
    output["none"] = set()
    for key, row in records.items():
        output[classify(row)].add(key)
    if sum(len(ids) for ids in output.values()) != len(records):
        raise RuntimeError("LEAD_QUEUE_PARTITION_COUNT_MISMATCH")
    return output

def patch_view_filter(path, token, wanted):
    """Patch only a managed view; report redacted Feishu API error codes."""
    from base_readonly_probe import ROOT
    body = json.dumps({"property": {"filter_info": wanted}},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ROOT + path, data=body, method="PATCH",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            obj = json.loads(exc.read().decode("utf-8"))
            code = obj.get("code", "unknown")
            detail = str(obj.get("msg", ""))[:90]
        except (ValueError, UnicodeError):
            code, detail = "unknown", "unavailable"
        raise RuntimeError(f"LEAD_QUEUE_FILTER_HTTP_{exc.code}_CODE_{code}_MSG_{detail}") from None
    require_success(result, "SET_QUEUE_FILTER")
    return result

def read_ids(root, token, view_id):
    ids = set()
    for rec in pages(root + "/records", token, {"view_id": view_id}):
        key = lead.norm((rec.get("fields") or {}).get("Lead ID"))
        if not key or key in ids:
            raise RuntimeError("LEAD_QUEUE_VISIBLE_ID_INVALID")
        ids.add(key)
    return ids

def main(apply=False):
    source = lead.sheets_data()  # stale source means no view writes
    token = lead.auth()
    tables = [t for t in pages(API + "/tables", token)
              if t.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_QUEUE_UNEXPECTED_TABLE")
    root = API + "/tables/" + EXPECTED_TABLE_ID
    fields = list(pages(root + "/fields", token))
    ids = {}
    for f in fields:
        name = f.get("field_name")
        if name in REQUIRED:
            if name in ids or f.get("type") != REQUIRED[name] or not f.get("field_id"):
                raise RuntimeError("LEAD_QUEUE_FIELD_SCHEMA_INVALID")
            ids[name] = f["field_id"]
    if set(ids) != set(REQUIRED):
        raise RuntimeError("LEAD_QUEUE_FIELDS_MISSING")

    records = {}
    for rec in pages(root + "/records", token):
        row = rec.get("fields") or {}
        key = lead.norm(row.get("Lead ID"))
        if not key or key in records or not rec.get("record_id"):
            raise RuntimeError("LEAD_QUEUE_DUPLICATE_ID")
        records[key] = row
    check_parity(source, records) # verifies all source-owned fields
    for row in records.values():
        for name in manual.MANUAL:
            manual.checked(row.get(name))
    partition = assert_queue_partition(records)
    counts = {k: len(v) for k,v in partition.items()}
    print("LEAD_QUEUE_SOURCE_SINK_PARITY_PASS=" +
          json.dumps({"total":len(source),"counts":counts},
                     ensure_ascii=False), flush=True)

    views = list(pages(root + "/views", token))
    for title, kind in QUEUES:
        existing = [v for v in views if v.get("view_name") == title]
        if len(existing) > 1:
            raise RuntimeError("LEAD_QUEUE_VIEW_NAME_DUPLICATE")
        view_id = existing[0].get("view_id") if existing else None
        wanted = queue_filter(ids, kind)
        if not view_id:
            if not apply:
                print("LEAD_QUEUE_MISSING_VIEW_DRY_RUN=" + title, flush=True)
                continue
            data = require_success(request("POST",root+"/views",token=token,
                 body={"view_name":title,"view_type":"grid"}), "CREATE_QUEUE_VIEW")
            view_id = (data.get("view") or {}).get("view_id") or data.get("view_id")
            if not view_id:
                raise RuntimeError("LEAD_QUEUE_CREATED_VIEW_MISSING_ID")
        view = get_one_view(root, token, view_id)
        if view.get("view_name") != title or view.get("view_type") != "grid":
            raise RuntimeError("LEAD_QUEUE_VIEW_TYPE_CHANGED")
        filt = (view.get("property") or {}).get("filter_info")
        if not conditions_equal(filt, wanted):
            if not apply:
                print("LEAD_QUEUE_FILTER_NEEDS_UPDATE="+title, flush=True)
                continue
            patch_view_filter(root+"/views/"+view_id,token,wanted)
            view = get_one_view(root, token, view_id)
            if not conditions_equal((view.get("property") or {}).get("filter_info"), wanted):
                raise RuntimeError("LEAD_QUEUE_FILTER_READBACK_MISMATCH")
        observed = read_ids(root,token,view_id)
        if observed != partition[kind]:
            raise RuntimeError("LEAD_QUEUE_FILTERED_RECORDS_MISMATCH_" + kind)
        print("LEAD_QUEUE_VIEW_VERIFIED=" + json.dumps({
            "name":title,"count":len(observed),
            "url":f"https://ocnz4cb25scn.feishu.cn/base/{BASE}?table={EXPECTED_TABLE_ID}&view={view_id}"
            },ensure_ascii=False), flush=True)
    print("LEAD_QUEUE_VIEW_AUDIT_PASS=1 MODE="+
          ("APPLY" if apply else "READ_ONLY"),flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        main(args.apply)
    except Exception as e:
        print("LEAD_QUEUE_VIEW_FAILED="+str(e),file=sys.stderr)
        sys.exit(1)
