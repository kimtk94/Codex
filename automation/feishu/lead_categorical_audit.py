#!/usr/bin/env python3
"""Read-only categorical audit of Lead Status and derived Follow-up Action.
No schema edits, source writes or mail sending.
"""
import collections
import json
import sys
import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
from sales_home_links import API, pages

TARGETS = ("Lead Status", "처리 방향")
KNOWN_ACTIONS = (
    "기존 메일 확인 / Follow-up 검토",
    "생성 이후 메일 발송 검토",
    "Description 검토 후 첫 메일 검토",
    "공통 안내 메일 검토",
)

def main():
    token = lead.auth()
    tables = [t for t in pages(API + "/tables", token) if t.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != manual.EXPECTED_TABLE_ID:
        raise RuntimeError("WRONG_LEAD_TABLE")
    root = API + "/tables/" + manual.EXPECTED_TABLE_ID
    fields = {f["field_name"]: f for f in pages(root + "/fields", token)}
    if any(x not in fields for x in TARGETS):
        raise RuntimeError("MISSING_FIELD")
    counts = {x: collections.Counter() for x in TARGETS}
    identifiers = set()
    for record in pages(root + "/records", token):
        d = record.get("fields") or {}
        key = lead.norm(d.get("Lead ID"))
        if not key or key in identifiers:
            raise RuntimeError("INVALID_LEAD_ID")
        identifiers.add(key)
        for name in TARGETS:
            counts[name][lead.norm(d.get(name))] += 1
    if len(identifiers) < 450:
        raise RuntimeError("ROW_COUNT_UNEXPECTED")
    action_unknown = {k: v for k,v in counts["처리 방향"].items() if k not in KNOWN_ACTIONS}
    result = {
        "rows":len(identifiers),
        "field_types":{x: fields[x]["type"] for x in TARGETS},
        "unique_values":{x:len(counts[x]) for x in TARGETS},
        "distributions":{x:dict(counts[x]) for x in TARGETS},
        "unknown_action_values":action_unknown,
        "read_only":True,
    }
    print("LEAD_CATEGORICAL_AUDIT=" + json.dumps(result, ensure_ascii=False), flush=True)
    if action_unknown:
        raise RuntimeError("ACTION_ENUM_HAS_UNKNOWN_VALUES")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("LEAD_CATEGORICAL_AUDIT_FAILED="+str(exc), file=sys.stderr)
        sys.exit(1)
