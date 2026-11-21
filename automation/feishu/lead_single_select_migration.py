#!/usr/bin/env python3
"""Guarded one-time Feishu Lead Text -> Single Select schema conversion.

Default is read-only. Conversion is opt-in via --apply, after the new writers
have been deployed. This tool edits no records, views, manual checkboxes,
SFDC objects, or mail. It rejects unknown option values and verifies complete
row-level parity after each schema change.
"""
import argparse
from copy import deepcopy
import json
import sys

import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
from sales_home_links import API, pages, request, require_success

TARGETS = lead.SINGLE_SELECT_OPTIONS

def validate(rows, fields):
    schema = {f["field_name"]: f for f in fields}
    if any(name not in schema or schema[name].get("type") not in (1, 3)
           or not schema[name].get("field_id") for name in TARGETS):
        raise RuntimeError("LEAD_SELECT_UNEXPECTED_FIELD_SCHEMA")
    if any(schema.get(name, {}).get("type") != 7 for name in manual.MANUAL):
        raise RuntimeError("LEAD_SELECT_MANUAL_SCHEMA_CONFLICT")
    if len(rows) < 450:
        raise RuntimeError("LEAD_SELECT_RECORD_COUNT_TOO_SMALL")
    ids = set()
    counts = {name: {x: 0 for x in values} for name, values in TARGETS.items()}
    for record in rows:
        values = record.get("fields") or {}
        key = lead.norm(values.get("Lead ID"))
        if not key or key in ids or not record.get("record_id"):
            raise RuntimeError("LEAD_SELECT_DUPLICATE_ID")
        ids.add(key)
        for name in TARGETS:
            value = lead.norm(values.get(name))
            if value not in counts[name]:
                raise RuntimeError("LEAD_SELECT_UNKNOWN_VALUE:" + name)
            counts[name][value] += 1
        for name in manual.MANUAL:
            manual.checked(values.get(name))
    return schema, counts

def snapshot(rows):
    return {
        lead.norm(rec["fields"]["Lead ID"]): {
            "record_id": rec["record_id"],
            "fields": deepcopy(rec["fields"]),
        } for rec in rows
    }

def parity(before, after):
    if set(before) != set(after):
        raise RuntimeError("LEAD_SELECT_RECORD_SET_CHANGED")
    for key in before:
        old, new = before[key], after[key]
        if old["record_id"] != new["record_id"]:
            raise RuntimeError("LEAD_SELECT_RECORD_ID_CHANGED")
        for name, value in old["fields"].items():
            if name in TARGETS:
                if lead.norm(value) != lead.norm(new["fields"].get(name)):
                    raise RuntimeError("LEAD_SELECT_OPTION_VALUE_LOST")
            elif value != new["fields"].get(name):
                raise RuntimeError("LEAD_SELECT_UNRELATED_FIELD_CHANGED")
    return len(before)

def main(apply=False):
    token = lead.auth()
    tables = [x for x in pages(API + "/tables", token)
              if x.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != manual.EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_SELECT_WRONG_TABLE")
    root = API + "/tables/" + manual.EXPECTED_TABLE_ID
    fields = list(pages(root + "/fields", token))
    before_rows = list(pages(root + "/records", token))
    schema, counts = validate(before_rows, fields)
    remaining = [name for name in TARGETS if schema[name]["type"] == 1]
    print("LEAD_SELECT_MIGRATION_PLAN=" + json.dumps({
        "table": manual.EXPECTED_TABLE_ID,
        "total": len(before_rows),
        "pending": remaining,
        "already_single_select": [x for x in TARGETS if x not in remaining],
        "distribution": counts,
        "apply": apply,
    }, ensure_ascii=False), flush=True)
    if not apply:
        print("LEAD_SELECT_DRY_RUN_NO_WRITES=true", flush=True)
        return
    baseline = snapshot(before_rows)
    for name in remaining:
        field_id = schema[name]["field_id"]
        body = lead.field_definition(name)
        # Feishu Bitable Update Field API. Existing option values must all
        # match before changing the type. Failure aborts immediately.
        require_success(request("PUT", root + "/fields/" + field_id,
                               token=token, body=body),
                        "UPDATE_LEAD_SINGLE_SELECT_FIELD")
        checked_fields = list(pages(root + "/fields", token))
        checked_rows = list(pages(root + "/records", token))
        validated_schema, new_counts = validate(checked_rows, checked_fields)
        if validated_schema[name]["type"] != 3 or counts != new_counts:
            raise RuntimeError("LEAD_SELECT_SCHEMA_READBACK_MISMATCH")
        parity(baseline, snapshot(checked_rows))
        print("LEAD_SELECT_FIELD_PASS=" + name, flush=True)
    print("LEAD_SELECT_ALL_READBACK_PASS=" + str(len(baseline)), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    try:
        main(apply=args.apply)
    except Exception as e:
        print("LEAD_SELECT_MIGRATION_FAILED=" + str(e), file=sys.stderr)
        sys.exit(1)
