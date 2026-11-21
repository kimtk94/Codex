#!/usr/bin/env python3
"""Idempotent, isolated Feishu Lead views with source/sink parity checks.

Only two explicitly managed, source-verified grid views, filtered to recent-year eligible Leads.
Never sends email, edits SFDC/QQ, creates an Account, deletes records, or
modifies other Feishu tables/views. Safe read-only mode by default.
"""
import argparse
import json
import sys
from collections import Counter

import lead_mail_description_sync as lead
import lead_eligibility as age
from sales_home_links import API, BASE, pages, request, require_success

TABLE = lead.TABLE
VIEWS = (
    ("01 · 발송 증거 없음 · Description 있음", "있음"),
    ("02 · 발송 증거 없음 · Description 없음", "없음"),
)
MAIL_CLASS = "메일 발송 증거 없음"
CHECK_FIELDS = (
    "Lead ID", "고객명", "Account (고객 입력 원문)", "Email",
    "Lead Created", "Lead Status", "Description", "Description 있음",
    "내 메일 연락 여부", "연락 구분", "생성 후 발송 횟수",
    "생성 전 발송 횟수", "최근 발송일", "메일 증거 Message-ID",
    "메일 수신 유형", "처리 방향", "메일 원본 확인시각",
)

def expected_ids(rows, description):
    today=age.today_kst()
    return {key for key, fields in rows.items()
            if fields["연락 구분"] == MAIL_CLASS
            and fields["Description 있음"] == description
            and age.eligibility(fields,today) == "eligible"}

def filter_definition(field_ids, description):
    return {"conjunction": "and", "conditions": [
        {"field_id": field_ids["연락 구분"], "operator": "is",
         "value": json.dumps([MAIL_CLASS], ensure_ascii=False)},
        {"field_id": field_ids["Description 있음"], "operator": "is",
         "value": json.dumps([description], ensure_ascii=False)},
        {"field_id": field_ids[age.ELIGIBILITY_FIELD], "operator": "is",
         "value": json.dumps([age.LABELS["eligible"]], ensure_ascii=False)},
    ]}

def filter_matches(observed, wanted):
    if not isinstance(observed, dict) or observed.get("conjunction") != "and":
        return False
    def to_conditions(value):
        result = set()
        for item in value.get("conditions") or []:
            if item.get("operator") != "is":
                return None
            val = item.get("value")
            try:
                parsed = json.loads(val) if isinstance(val, str) else val
            except (TypeError, ValueError):
                return None
            if not isinstance(parsed, list) or len(parsed) != 1:
                return None
            result.add((item.get("field_id"), parsed[0]))
        return result
    return to_conditions(observed) == to_conditions(wanted)

def check_parity(source, feishu):
    if len(source) < 450 or len(source) != len(feishu):
        raise RuntimeError("LEAD_SOURCE_SINK_ROW_COUNT_MISMATCH")
    if set(source) != set(feishu):
        raise RuntimeError("LEAD_SOURCE_SINK_ID_MISMATCH")
    for key, row in source.items():
        fields = feishu[key]
        for field in CHECK_FIELDS:
            if lead.norm(fields.get(field)) != row[field]:
                raise RuntimeError("LEAD_SOURCE_SINK_VALUE_MISMATCH")
    return Counter((r["연락 구분"], r["Description 있음"]) for r in source.values())

def get_one_view(root, token, view_id):
    data = require_success(request("GET", root + "/views/" + view_id,
                                   token=token), "GET_LEAD_VIEW")
    view = data.get("view") or {}
    if view.get("view_id") != view_id:
        raise RuntimeError("LEAD_VIEW_READBACK_ID_MISMATCH")
    return view

def main(apply=False):
    # Google source freshness is checked before ANY Feishu write.
    source = lead.sheets_data()
    token = lead.auth()
    tables = [r for r in pages(API + "/tables", token) if r.get("name") == TABLE]
    if len(tables) != 1:
        raise RuntimeError("EXACTLY_ONE_LEAD_TABLE_REQUIRED")
    table_id = tables[0].get("table_id")
    root = API + "/tables/" + table_id
    fields = list(pages(root + "/fields", token))
    ids = {f.get("field_name"): f.get("field_id") for f in fields
           if f.get("type") == 1 and f.get("field_id")}
    if not {"연락 구분", "Description 있음", age.ELIGIBILITY_FIELD} <= set(ids):
        raise RuntimeError("LEAD_FILTER_FIELDS_MISSING_OR_WRONG_TYPE")

    originals = list(pages(root + "/records", token))
    observed = {}
    for rec in originals:
        row = rec.get("fields") or {}
        key = lead.norm(row.get("Lead ID"))
        if not key or key in observed or not rec.get("record_id"):
            raise RuntimeError("FEISHU_LEAD_KEY_DUPLICATED_OR_MISSING")
        observed[key] = row
    counts = check_parity(source, observed)
    today=age.today_kst()
    for key,row in source.items():
        if lead.norm(observed[key].get(age.ELIGIBILITY_FIELD)) != age.label(row,today):
            raise RuntimeError("LEAD_CONTACT_ELIGIBILITY_SINK_MISMATCH")
    current_eligibility=age.stats(source.values(),today)
    print("LEAD_CONTACT_AGE_WINDOW="+json.dumps(current_eligibility,ensure_ascii=False),flush=True)
    print("LEAD_VIEWS_SOURCE_SINK_PARITY_PASS=" +
          json.dumps({"records": len(source),
            "mail_no_evidence_desc_present": counts[(MAIL_CLASS, "있음")],
            "mail_no_evidence_desc_missing": counts[(MAIL_CLASS, "없음")]},
            ensure_ascii=False), flush=True)

    views = list(pages(root + "/views", token))
    names = [v.get("view_name") for v in views]
    for name, description in VIEWS:
        if names.count(name) > 1:
            raise RuntimeError("DUPLICATE_MANAGED_LEAD_VIEW")
        matches = [v for v in views if v.get("view_name") == name]
        view_id = matches[0].get("view_id") if matches else None
        wanted = filter_definition(ids, description)
        if not view_id and not apply:
            print("LEAD_VIEW_MISSING_DRY_RUN=" + name, flush=True)
            continue
        if not view_id:
            result = require_success(request("POST", root + "/views", token=token,
                body={"view_name": name, "view_type": "grid"}), "CREATE_LEAD_VIEW")
            new = result.get("view") or {}
            view_id = new.get("view_id") or result.get("view_id")
            if not view_id:
                raise RuntimeError("CREATED_LEAD_VIEW_ID_MISSING")
        view = get_one_view(root, token, view_id)
        if view.get("view_type") != "grid" or view.get("view_name") != name:
            raise RuntimeError("LEAD_VIEW_TYPE_OR_NAME_CHANGED")
        if not filter_matches((view.get("property") or {}).get("filter_info"), wanted):
            if not apply:
                print("LEAD_VIEW_FILTER_NEEDS_UPDATE=" + name, flush=True)
                continue
            require_success(request("PATCH", root + "/views/" + view_id,
                token=token, body={"property": {"filter_info": wanted}}),
                "SET_LEAD_VIEW_FILTER")
            view = get_one_view(root, token, view_id)
            if not filter_matches((view.get("property") or {}).get("filter_info"), wanted):
                raise RuntimeError("LEAD_VIEW_FILTER_READBACK_MISMATCH")
        actual_ids = set()
        for record in pages(root + "/records", token, {"view_id": view_id}):
            key = lead.norm((record.get("fields") or {}).get("Lead ID"))
            if not key or key in actual_ids:
                raise RuntimeError("LEAD_VIEW_DUPLICATE_OR_MISSING_KEY")
            actual_ids.add(key)
        expected = expected_ids(source, description)
        if actual_ids != expected:
            raise RuntimeError("LEAD_VIEW_VISIBLE_RECORD_MISMATCH")
        print("LEAD_VIEW_VERIFIED=" + json.dumps({"view": name, "count": len(expected),
            "url": f"https://ocnz4cb25scn.feishu.cn/base/{BASE}?table={table_id}&view={view_id}"},
            ensure_ascii=False), flush=True)
    print("LEAD_VIEW_AUDIT_PASS=1 MODE=" + ("APPLY" if apply else "READ_ONLY"), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arg = parser.parse_args()
    try:
        main(arg.apply)
    except Exception as exc:
        print("LEAD_VIEW_SYNC_FAILED=" + str(exc), file=sys.stderr)
        sys.exit(1)
