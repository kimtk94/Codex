#!/usr/bin/env python3
"""Isolated Lead workbench column visibility audit/update.

Only target view '00 · Lead 업무 통합 · 최근 1년'. Hide nonessential
fields by PATCH property.hidden_fields. No record/field schema changes.
Feishu server View API exposes hidden_fields but does not guarantee order;
report column ordering as unsupported rather than pretending to set it.
"""
import argparse
import json
import sys

import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
import lead_workbench_view as workbench
from lead_mail_views_sync import get_one_view, filter_matches
from sales_home_links import API, pages, request, require_success

# Ordered design intent; the PATCH endpoint applies visibility only.
VISIBLE = (
    "Lead ID", "고객명", "Account (고객 입력 원문)", "Email",
    "Lead Created", "Lead Status", "Description 있음", "Description",
    "연락 구분", "Lead 업무 우선순위 (자동)",
    "재연락 필요", "메일 발송 예정", "검토 완료",
    "최근 발송일", "처리 방향",
)
REQUIRED = set(VISIBLE)
MIN_FIELDS = 18

def make_plan(fields):
    names = [f.get("field_name") for f in fields]
    if len(fields) < MIN_FIELDS or len(set(names)) != len(names):
        raise RuntimeError("LEAD_COLUMNS_BAD_FIELD_COUNT_OR_DUPLICATE")
    by_name = {f["field_name"]: f for f in fields}
    if not REQUIRED <= set(by_name):
        raise RuntimeError("LEAD_COLUMNS_VISIBLE_REQUIRED_MISSING")
    if any(not f.get("field_id") for f in fields):
        raise RuntimeError("LEAD_COLUMNS_FIELD_ID_MISSING")
    if any(by_name[k].get("type") != 7 for k in manual.MANUAL):
        raise RuntimeError("LEAD_COLUMNS_MANUAL_SCHEMA_WRONG")
    if any(by_name[k].get("type") != 3 for k in ("Lead Status", "Description 있음", "연락 구분", "처리 방향")):
        raise RuntimeError("LEAD_COLUMNS_SELECT_SCHEMA_WRONG")
    # First field is the index/primary field: never hide.
    first = fields[0]["field_name"]
    if first not in REQUIRED:
        raise RuntimeError("LEAD_COLUMNS_PRIMARY_NOT_VISIBLE")
    return [f["field_id"] for f in fields if f["field_name"] not in REQUIRED]

def verify_hidden(view, expected):
    p = view.get("property") or {}
    hidden = p.get("hidden_fields")
    if hidden is None:
        hidden = []
    if not isinstance(hidden, list) or len(set(hidden)) != len(hidden):
        raise RuntimeError("LEAD_COLUMNS_HIDDEN_FIELDS_MALFORMED")
    if set(hidden) != set(expected):
        raise RuntimeError("LEAD_COLUMNS_HIDDEN_READBACK_MISMATCH")
    return len(hidden)

def main(apply=False):
    token = lead.auth()
    tables = [t for t in pages(API + "/tables", token) if t.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != manual.EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_COLUMNS_WRONG_TABLE")
    root = API + "/tables/" + manual.EXPECTED_TABLE_ID
    fields = list(pages(root + "/fields", token))
    target = make_plan(fields)
    eligible_id = workbench.validate_schema(fields)
    views = list(pages(root + "/views", token))
    target_views = [v for v in views if v.get("view_name") == workbench.VIEW_NAME]
    if len(target_views) != 1 or not target_views[0].get("view_id"):
        raise RuntimeError("LEAD_COLUMNS_WORKBENCH_VIEW_NOT_UNIQUE")
    view_id = target_views[0]["view_id"]
    before = get_one_view(root, token, view_id)
    if not filter_matches((before.get("property") or {}).get("filter_info"),
                          workbench.filter_definition(eligible_id)):
        raise RuntimeError("LEAD_COLUMNS_ELIGIBILITY_FILTER_CHANGED")
    others = {v.get("view_id"): v.get("view_name") for v in views if v.get("view_id") != view_id}
    old_hidden = (before.get("property") or {}).get("hidden_fields") or []
    if not isinstance(old_hidden, list):
        raise RuntimeError("LEAD_COLUMNS_PREVIOUS_HIDDEN_MALFORMED")
    changes = set(old_hidden) != set(target)
    print("LEAD_COLUMNS_PLAN=" + json.dumps({
        "view_id": view_id, "total_fields": len(fields),
        "desired_visible": list(VISIBLE), "hidden_count": len(target),
        "existing_hidden_count": len(old_hidden), "needs_change": changes,
        "other_views": len(others), "ordering": "not_applied_by_this_API",
        "apply": apply,
    }, ensure_ascii=False), flush=True)
    if changes and apply:
        require_success(request("PATCH", root + "/views/" + view_id,
                                token=token, body={"property": {"hidden_fields": target}}),
                        "LEAD_COLUMNS_PATCH_TARGET_VIEW")
    elif changes:
        print("LEAD_COLUMNS_DRY_RUN_NO_WRITES=true", flush=True)
        return
    after = get_one_view(root, token, view_id)
    verify_hidden(after, target)
    if not filter_matches((after.get("property") or {}).get("filter_info"),
                          workbench.filter_definition(eligible_id)):
        raise RuntimeError("LEAD_COLUMNS_FILTER_LOST")
    current_views = list(pages(root + "/views", token))
    now_others = {v.get("view_id"): v.get("view_name") for v in current_views
                  if v.get("view_id") != view_id}
    if now_others != others:
        raise RuntimeError("LEAD_COLUMNS_OTHER_VIEWS_CHANGED")
    print("LEAD_COLUMNS_READBACK_PASS=" + json.dumps({
        "view_id": view_id, "visible": len(VISIBLE),
        "hidden": len(target), "other_views_preserved": len(others),
        "url": "https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table="
               + manual.EXPECTED_TABLE_ID + "&view=" + view_id,
    }, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    try:
        main(p.parse_args().apply)
    except Exception as e:
        print("LEAD_COLUMNS_FAILED=" + str(e), file=sys.stderr)
        sys.exit(1)
