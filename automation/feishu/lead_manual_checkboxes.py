#!/usr/bin/env python3
"""Provision/audit three USER-OWNED Feishu Lead checkboxes, never their values.

Scope: exact Novogene sales Base + unique dedicated Lead table. No mutation
outside missing checkbox field definitions. No record create/update/delete.
Default: read-only; --apply adds missing checkbox columns idempotently.
"""
import argparse
import json
import sys
from collections import Counter

import lead_mail_description_sync as lead
from sales_home_links import API, BASE, pages, request, require_success

TABLE = lead.TABLE
MANUAL = ("검토 완료", "메일 발송 예정", "재연락 필요")
CHECKBOX_TYPE = 7
EXPECTED_TABLE_ID = "tblanxghmeeKJGRO"

def checked(value):
    # Feishu checkbox values must be boolean; an unset value is equivalent
    # to unchecked. Never coerce the string 'false' to True.
    if value is None:
        return False
    if type(value) is not bool:
        raise RuntimeError("MANUAL_CHECKBOX_VALUE_NOT_BOOLEAN")
    return value

def audit_records(records, manual_fields):
    values = {}
    for rec in records:
        fields = rec.get("fields") or {}
        key = lead.norm(fields.get("Lead ID"))
        if not key or key in values or not rec.get("record_id"):
            raise RuntimeError("LEAD_MANUAL_ROW_ID_INTEGRITY")
        values[key] = {field: checked(fields.get(field))
                       for field in manual_fields}
    if len(values) < 450:
        raise RuntimeError("LEAD_MANUAL_SOURCE_ROW_COUNT_TOO_SMALL")
    return values

def assert_unchanged(before, after):
    if set(before) != set(after):
        raise RuntimeError("LEAD_MANUAL_ROW_SET_CHANGED")
    for key, values in before.items():
        for field, flag in values.items():
            if field not in after[key] or after[key][field] != flag:
                raise RuntimeError("LEAD_MANUAL_SELECTION_CHANGED")

def verify_schema(fields):
    by_name = {}
    for f in fields:
        name = f.get("field_name")
        if name in MANUAL:
            if name in by_name:
                raise RuntimeError("LEAD_MANUAL_DUPLICATE_FIELD")
            by_name[name] = f.get("type")
    if any(value != CHECKBOX_TYPE for value in by_name.values()):
        raise RuntimeError("LEAD_MANUAL_FIELD_TYPE_CONFLICT")
    return tuple(field for field in MANUAL if field not in by_name)

def main(apply=False):
    token = lead.auth()
    tables = [t for t in pages(API + "/tables", token)
              if t.get("name") == TABLE]
    if len(tables) != 1:
        raise RuntimeError("LEAD_MANUAL_TABLE_NOT_UNIQUE")
    table_id = tables[0].get("table_id")
    if table_id != EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_MANUAL_UNEXPECTED_TABLE_ID")
    root = API + "/tables/" + table_id
    fields = list(pages(root + "/fields", token))
    missing = verify_schema(fields)
    present = tuple(field for field in MANUAL if field not in missing)
    before = audit_records(list(pages(root + "/records", token)), present)
    print("LEAD_MANUAL_PRECHECK=" + json.dumps({
        "rows": len(before), "existing_checkbox_fields": len(present),
        "missing_fields": list(missing), "mode": "APPLY" if apply else "READ_ONLY"
    }, ensure_ascii=False), flush=True)
    if not apply:
        return
    for name in missing:
        require_success(request("POST", root + "/fields", token=token,
            body={"field_name": name, "type": CHECKBOX_TYPE}),
            "CREATE_LEAD_MANUAL_CHECKBOX")
        print("LEAD_MANUAL_FIELD_CREATED=" + name, flush=True)
    fields_after = list(pages(root + "/fields", token))
    if verify_schema(fields_after):
        raise RuntimeError("LEAD_MANUAL_SCHEMA_READBACK_INCOMPLETE")
    after = audit_records(list(pages(root + "/records", token)), MANUAL)
    assert_unchanged(before, after)
    counts = Counter({field: sum(values[field] for values in after.values())
                      for field in MANUAL})
    print("LEAD_MANUAL_CHECKBOX_READBACK_PASS=" + json.dumps({
        "rows": len(after), "checked_counts": counts,
        "no_record_writes": True,
        "table_url": f"https://ocnz4cb25scn.feishu.cn/base/{BASE}?table={table_id}"
    }, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    try:
        main(apply=args.apply)
    except Exception as exc:
        print("LEAD_MANUAL_CHECKBOX_FAILED=" + str(exc), file=sys.stderr)
        sys.exit(1)
