#!/usr/bin/env python3
"""Frequent Feishu-only delta synchronization of Lead action queue labels.

Uses the existing verified, dedicated Lead table and its user-owned checkboxes.
Never accesses QQ IMAP, edits SFDC, sends mail, or alters other Feishu tables.
Only writes the derived 'Lead 업무 우선순위 (자동)' field for changed records.\nDeployment is safe to repeat: unchanged rows cause no Feishu record writes.
A source timestamp and all existing view definitions must be valid first.
"""
import argparse
import datetime as dt
import json
import sys

import lead_action_queue_views as queue
import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
from lead_mail_views_sync import CHECK_FIELDS, get_one_view, filter_matches
from sales_home_links import API, pages, request, require_success

SOURCE_STALE_HOURS = 72
MAX_FRACTION_CHANGED = 0.25
MIN_ALLOWED_UPDATES = 100
NO_CHANGE = "NO_NEW_DATA"

def source_stamps_fresh(records, now=None):
    """A successful poll is not evidence of freshness: validate mail timestamps."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not records:
        raise RuntimeError("LEAD_DELTA_EMPTY_SOURCE")
    timestamps = {lead.norm(row.get("메일 원본 확인시각")) for row in records.values()}
    if "" in timestamps:
        raise RuntimeError("LEAD_DELTA_SOURCE_TIMESTAMP_MISSING")
    for stamp in timestamps:
        try:
            value = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            raise RuntimeError("LEAD_DELTA_SOURCE_TIMESTAMP_INVALID") from None
        if value.tzinfo is None:
            raise RuntimeError("LEAD_DELTA_SOURCE_TIMESTAMP_NAIVE")
        age = now - value.astimezone(dt.timezone.utc)
        if age < dt.timedelta(minutes=-5):
            raise RuntimeError("LEAD_DELTA_SOURCE_TIMESTAMP_FUTURE")
        if age > dt.timedelta(hours=SOURCE_STALE_HOURS):
            raise RuntimeError("LEAD_DELTA_SOURCE_STALE")
    return len(timestamps)

def schema_check(fields):
    required = {
        "Lead ID": 1, "Lead Status": 1, "연락 구분": 1,
        "메일 원본 확인시각": 1, queue.QUEUE_FIELD: 1,
        **{name: 7 for name in manual.MANUAL},
    }
    names = {}
    for field in fields:
        name = field.get("field_name")
        if name in required:
            if name in names or field.get("type") != required[name]:
                raise RuntimeError("LEAD_DELTA_FIELD_SCHEMA_CONFLICT")
            names[name] = field.get("field_id")
    if any(not names.get(name) for name in required):
        raise RuntimeError("LEAD_DELTA_FIELD_MISSING")
    return names[queue.QUEUE_FIELD]

def plan_changes(records):
    if len(records) < 450:
        raise RuntimeError("LEAD_DELTA_UNEXPECTED_LEAD_COUNT")
    changes = []
    for key, record in records.items():
        row = record["fields"]
        expected = queue.QUEUE_LABELS[queue.classify(row)]
        if lead.norm(row.get(queue.QUEUE_FIELD)) != expected:
            changes.append({"record_id": record["record_id"],
                            "fields": {queue.QUEUE_FIELD: expected}})
    return changes

def guard_delta_size(changes, total):
    limit = max(MIN_ALLOWED_UPDATES, int(total * MAX_FRACTION_CHANGED))
    if len(changes) > limit:
        raise RuntimeError("LEAD_DELTA_TOO_MANY_CHANGES_USE_FULL_SYNC")
    return limit

def check_preservation(old, new):
    if set(old) != set(new):
        raise RuntimeError("LEAD_DELTA_RECORDS_CHANGED")
    before = {key: rec["fields"] for key, rec in old.items()}
    after = {key: rec["fields"] for key, rec in new.items()}
    for key, old_row in before.items():
        new_row = after[key]
        for name in CHECK_FIELDS:
            if lead.norm(old_row.get(name)) != lead.norm(new_row.get(name)):
                raise RuntimeError("LEAD_DELTA_SOURCE_FIELD_CHANGED")
    if queue.manual_snapshot(before) != queue.manual_snapshot(after):
        raise RuntimeError("LEAD_DELTA_MANUAL_FIELD_CHANGED")
    for key, fields in after.items():
        desired = queue.QUEUE_LABELS[queue.classify(fields)]
        if lead.norm(fields.get(queue.QUEUE_FIELD)) != desired:
            raise RuntimeError("LEAD_DELTA_PRIORITY_READBACK_MISMATCH")
    return after

def validate_views(root, token, field_id):
    views = list(pages(root + "/views", token))
    names = [x.get("view_name") for x in views]
    for title, kind in queue.QUEUES:
        if names.count(title) != 1:
            raise RuntimeError("LEAD_DELTA_QUEUE_VIEW_NOT_UNIQUE")
        view_id = next(x.get("view_id") for x in views if x.get("view_name") == title)
        view = get_one_view(root, token, view_id)
        if (view.get("view_name") != title or view.get("view_type") != "grid"
                or not filter_matches((view.get("property") or {}).get("filter_info"),
                                      queue.filter_definition(field_id, kind))):
            raise RuntimeError("LEAD_DELTA_VIEW_FILTER_DRIFT")
    return {v.get("view_name"): v.get("view_id") for v in views}

def verify_view_ids(root, token, labels, views):
    groups = queue.partition(labels)
    for title, kind in queue.QUEUES:
        actual = queue.read_view_ids(root, token, views[title])
        if actual != groups[kind]:
            raise RuntimeError("LEAD_DELTA_VIEW_IDS_MISMATCH")
    return {kind: len(ids) for kind, ids in groups.items()}

def main(apply=False):
    token = lead.auth()
    tables = [x for x in pages(API + "/tables", token)
              if x.get("name") == lead.TABLE]
    if len(tables) != 1 or tables[0].get("table_id") != queue.EXPECTED_TABLE_ID:
        raise RuntimeError("LEAD_DELTA_WRONG_TABLE")
    root = API + "/tables/" + queue.EXPECTED_TABLE_ID
    field_id = schema_check(list(pages(root + "/fields", token)))
    old = queue.load_records(root, token)
    old_fields = {key: rec["fields"] for key, rec in old.items()}
    stamps = source_stamps_fresh(old_fields)
    views = validate_views(root, token, field_id)
    changes = plan_changes(old)
    max_changed = guard_delta_size(changes, len(old))
    before = queue.partition(old_fields)
    print("LEAD_DELTA_PLAN=" + json.dumps({
        "records": len(old), "source_stamps": stamps,
        "pending_updates": len(changes), "allowed_max": max_changed,
        "counts_before": {k: len(v) for k, v in before.items()},
        "apply": apply
    }, ensure_ascii=False), flush=True)

    if not apply:
        print("LEAD_DELTA_READ_ONLY_PASS=1", flush=True)
        return
    if not changes:
        # No writes, but ensure that even a no-op run has a correct source/view basis.
        print("LEAD_DELTA_NO_NEW_DATA=1 checked=" + str(len(old)), flush=True)
        return
    for start in range(0, len(changes), 100):
        batch = changes[start:start+100]
        require_success(request("POST", root + "/records/batch_update",
                                token=token, body={"records":batch}), "LEAD_DELTA_BATCH_UPDATE")
        print("LEAD_DELTA_APPLY_PROGRESS="+str(min(start+len(batch), len(changes)))+
              "/"+str(len(changes)), flush=True)
    new = queue.load_records(root, token)
    verified = check_preservation(old, new)
    stats = verify_view_ids(root, token, verified, views)
    print("LEAD_DELTA_READBACK_PASS=" + json.dumps({
        "records":len(new), "changed":len(changes), "counts_after":stats,
        "manual_selections_preserved":True, "other_tables_touched":False,
    }, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arg = parser.parse_args()
    try:
        main(apply=arg.apply)
    except Exception as exc:
        print("LEAD_DELTA_FAILED="+str(exc), file=sys.stderr)
        sys.exit(1)
