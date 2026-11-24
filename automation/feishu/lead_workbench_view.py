#!/usr/bin/env python3
"""Single entrypoint grid for the existing Lead workflow.

Creates/maintains exactly one additional overview view in the dedicated Lead
table. Existing seven queue/evidence views, records, manual checkboxes, and
any other table remain untouched. Read-only unless --apply is passed.
"""
import argparse
import json
import sys
import lead_action_queue_views as queue
import lead_eligibility as age
import lead_mail_description_sync as lead
from lead_mail_views_sync import filter_matches, get_one_view, check_parity
from sales_home_links import API, BASE, pages, request, require_success

VIEW_NAME = "00 · Lead 업무 통합 · 최근 1년"

def filter_definition(field_id):
    return {"conjunction": "and", "conditions": [{
        "field_id": field_id, "operator": "is",
        "value": json.dumps([age.LABELS["eligible"]], ensure_ascii=False),
    }]}

def expected_ids(rows, today=None):
    today = today or age.today_kst()
    return {key for key, row in rows.items()
            if age.eligibility(row, today) == "eligible"}

def validate_schema(fields):
    names = [f.get("field_name") for f in fields]
    required = (age.ELIGIBILITY_FIELD, queue.QUEUE_FIELD,
                "연락 구분", "Description 있음", "Lead Status",
                *queue.manual.MANUAL)
    if any(names.count(x) != 1 for x in required):
        raise RuntimeError("LEAD_OVERVIEW_REQUIRED_FIELD_MISSING_OR_DUPLICATE")
    by_name = {f["field_name"]: f for f in fields}
    for name in (age.ELIGIBILITY_FIELD, queue.QUEUE_FIELD):
        if by_name[name].get("type") != 1:
            raise RuntimeError("LEAD_OVERVIEW_DERIVED_FIELD_TYPE")
    for name in ("연락 구분", "Description 있음", "Lead Status"):
        if by_name[name].get("type") != 3:
            raise RuntimeError("LEAD_OVERVIEW_SELECT_FIELD_TYPE")
    for name in queue.manual.MANUAL:
        if by_name[name].get("type") != 7:
            raise RuntimeError("LEAD_OVERVIEW_MANUAL_FIELD_TYPE")
    field_id = by_name[age.ELIGIBILITY_FIELD].get("field_id")
    if not field_id:
        raise RuntimeError("LEAD_OVERVIEW_ELIGIBILITY_FIELD_ID_MISSING")
    return field_id

def verify_rows(rows):
    if len(rows) < 450:
        raise RuntimeError("LEAD_OVERVIEW_TOO_FEW_RECORDS")
    for key, row in rows.items():
        for flag in queue.manual.MANUAL:
            queue.manual.checked(row.get(flag))
        wanted = queue.QUEUE_LABELS[queue.classify(row)]
        if lead.norm(row.get(queue.QUEUE_FIELD)) != wanted:
            raise RuntimeError("LEAD_OVERVIEW_QUEUE_STALE")
        if lead.norm(row.get(age.ELIGIBILITY_FIELD)) != age.label(row):
            raise RuntimeError("LEAD_OVERVIEW_AGE_STALE")
    return len(rows)

def main(apply=False):
    source = lead.sheets_data()
    token = lead.auth()
    tables = [x for x in pages(API + "/tables", token)
              if x.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != queue.EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_OVERVIEW_WRONG_TABLE")
    root = API + "/tables/" + queue.EXPECTED_TABLE_ID
    field_id = validate_schema(list(pages(root + "/fields", token)))
    observed = queue.load_records(root, token)
    rows = {key: item["fields"] for key, item in observed.items()}
    check_parity(source, rows)
    verify_rows(rows)
    expected = expected_ids(rows)
    views = list(pages(root + "/views", token))
    matches = [x for x in views if x.get("view_name") == VIEW_NAME]
    if len(matches) > 1:
        raise RuntimeError("LEAD_OVERVIEW_DUPLICATE_VIEW")
    view_id = matches[0].get("view_id") if matches else None
    wanted = filter_definition(field_id)
    print("LEAD_OVERVIEW_PLAN=" + json.dumps({
        "total": len(rows),
        "eligible": len(expected),
        "expired": len(rows) - len(expected),
        "existing_view": bool(view_id),
        "other_views_untouched": True,
        "apply": apply,
    }, ensure_ascii=False), flush=True)
    if not view_id:
        if not apply:
            print("LEAD_OVERVIEW_MISSING_DRY_RUN=true", flush=True)
            return
        answer = require_success(request("POST", root + "/views",
                token=token, body={"view_name": VIEW_NAME, "view_type": "grid"}),
                "CREATE_LEAD_OVERVIEW_VIEW")
        view_id = (answer.get("view") or {}).get("view_id") or answer.get("view_id")
        if not view_id:
            raise RuntimeError("LEAD_OVERVIEW_CREATED_ID_MISSING")
    view = get_one_view(root, token, view_id)
    if view.get("view_name") != VIEW_NAME or view.get("view_type") != "grid":
        raise RuntimeError("LEAD_OVERVIEW_VIEW_IDENTITY_MISMATCH")
    if not filter_matches((view.get("property") or {}).get("filter_info"), wanted):
        if not apply:
            print("LEAD_OVERVIEW_FILTER_PENDING_READ_ONLY=true", flush=True)
            return
        require_success(request("PATCH", root + "/views/" + view_id,
            token=token, body={"property": {"filter_info": wanted}}),
            "SET_LEAD_OVERVIEW_FILTER")
        view = get_one_view(root, token, view_id)
        if not filter_matches((view.get("property") or {}).get("filter_info"), wanted):
            raise RuntimeError("LEAD_OVERVIEW_FILTER_READBACK_MISMATCH")
    actual = queue.read_view_ids(root, token, view_id)
    if actual != expected:
        raise RuntimeError("LEAD_OVERVIEW_VISIBLE_IDS_MISMATCH")
    print("LEAD_OVERVIEW_READBACK_PASS=" + json.dumps({
        "visible": len(actual),
        "source": len(rows),
        "excluded_over_year": len(rows) - len(actual),
        "url": f"https://ocnz4cb25scn.feishu.cn/base/{BASE}?table={queue.EXPECTED_TABLE_ID}&view={view_id}",
    }, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        main(args.apply)
    except Exception as exc:
        print("LEAD_OVERVIEW_FAILED=" + str(exc), file=sys.stderr)
        sys.exit(1)
