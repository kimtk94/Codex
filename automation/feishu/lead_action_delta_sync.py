#!/usr/bin/env python3
"""Frequent Feishu-only delta synchronization of Lead action queue labels.

Uses the existing verified, dedicated Lead table and its user-owned checkboxes.
Never accesses QQ IMAP, edits SFDC, sends mail, or alters other Feishu tables.
Only writes the derived 'Lead 업무 우선순위 (자동)' field for changed records.
The one-checkbox canary changes memory only, never a real Feishu checkbox.
Deployment is safe to repeat: unchanged rows cause no Feishu record writes, and views are verified.
The same rolling calendar-year cutoff is re-evaluated on each poll, with source and view guards.
"""
import argparse
import datetime as dt
import json
import sys

import lead_action_queue_views as queue
import lead_mail_description_sync as lead
import lead_manual_checkboxes as manual
import lead_eligibility as age
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
        "Lead ID": 1, "Lead Status": 1, "Lead Created": 1,
        "연락 구분": 3, "메일 원본 확인시각": 1,
        queue.QUEUE_FIELD: 1, age.ELIGIBILITY_FIELD: 1,
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
    today = age.today_kst()
    for key, record in records.items():
        row = record["fields"]
        expected = queue.QUEUE_LABELS[queue.classify(row, today)]
        eligible = age.label(row, today)
        altered = {}
        if lead.norm(row.get(queue.QUEUE_FIELD)) != expected:
            altered[queue.QUEUE_FIELD] = expected
        if lead.norm(row.get(age.ELIGIBILITY_FIELD)) != eligible:
            altered[age.ELIGIBILITY_FIELD] = eligible
        if altered:
            changes.append({"record_id": record["record_id"], "fields": altered})
    return changes

def simulate_single_manual_change(records):
    """Use real Feishu schema and records, but flip one checkbox in memory only.

    No production update request can be reached from this function. Printed
    evidence contains only aggregate counts; no Lead IDs or customer data.
    """
    from copy import deepcopy
    baseline = plan_changes(records)
    if baseline:
        raise RuntimeError("LEAD_DELTA_SIMULATION_BASELINE_NOT_CLEAN")
    selected = next((key for key, record in records.items()
                     if queue.classify(record["fields"]) == "review"), None)
    if selected is None:
        raise RuntimeError("LEAD_DELTA_SIMULATION_NO_ELIGIBLE_REVIEW")
    before = {key: record["fields"] for key, record in records.items()}
    original_flags = queue.manual_snapshot(before)
    scenario = deepcopy(records)
    if manual.checked(scenario[selected]["fields"].get("메일 발송 예정")):
        raise RuntimeError("LEAD_DELTA_SIMULATION_EXPECTED_UNCHECKED")
    scenario[selected]["fields"]["메일 발송 예정"] = True
    changed = plan_changes(scenario)
    if (len(changed) != 1 or changed[0]["record_id"] != records[selected]["record_id"]
            or changed[0]["fields"] != {queue.QUEUE_FIELD: queue.QUEUE_LABELS["planned"]}):
        raise RuntimeError("LEAD_DELTA_SIMULATION_EXACT_ONE_CHANGE_FAILED")
    after = {key: record["fields"] for key, record in scenario.items()}
    prior_counts = {k: len(v) for k, v in queue.partition(before).items()}
    simulated_counts = {k: len(v) for k, v in queue.partition(after).items()}
    if (simulated_counts["review"] != prior_counts["review"] - 1
            or simulated_counts["planned"] != prior_counts["planned"] + 1
            or queue.manual_snapshot(before) != original_flags):
        raise RuntimeError("LEAD_DELTA_SIMULATION_COUNTS_OR_SOURCE_CHANGED")
    return {
        "mode": "SIMULATION_ONLY",
        "source_records": len(records),
        "simulated_checkbox_flips": 1,
        "expected_derived_field_updates": 1,
        "real_feishu_writes": 0,
        "manual_selection_preserved": True,
        "scenario_before": prior_counts,
        "scenario_after": simulated_counts,
    }

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
        if lead.norm(fields.get(age.ELIGIBILITY_FIELD)) != age.label(fields):
            raise RuntimeError("LEAD_DELTA_ELIGIBILITY_READBACK_MISMATCH")
    return after

def validate_prewrite_snapshot(previous, latest):
    """Fail closed if a human or another sync changed source inputs mid-run.

    Never write from a stale view of manually selected follow-up flags.
    The auto-owned priority label may change; the newest value is replanned.
    """
    if set(previous) != set(latest):
        raise RuntimeError("LEAD_DELTA_CONCURRENT_RECORD_SET_CHANGE")
    original = {key: rec["fields"] for key, rec in previous.items()}
    updated = {key: rec["fields"] for key, rec in latest.items()}
    if queue.manual_snapshot(original) != queue.manual_snapshot(updated):
        raise RuntimeError("LEAD_DELTA_CONCURRENT_MANUAL_CHANGE")
    for key in original:
        if previous[key]["record_id"] != latest[key]["record_id"]:
            raise RuntimeError("LEAD_DELTA_CONCURRENT_RECORD_ID_CHANGE")
        for field in CHECK_FIELDS:
            if lead.norm(original[key].get(field)) != lead.norm(updated[key].get(field)):
                raise RuntimeError("LEAD_DELTA_CONCURRENT_SOURCE_CHANGE")
    return len(latest)

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

def main(apply=False, simulate_one=False):
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
    source_times = sorted(dt.datetime.fromisoformat(
        lead.norm(row["메일 원본 확인시각"]).replace("Z", "+00:00")
    ).astimezone(dt.timezone.utc) for row in old_fields.values())
    print("LEAD_DELTA_SOURCE_EVIDENCE=" + json.dumps({
        "earliest_mail_checked_at": source_times[0].isoformat(),
        "latest_mail_checked_at": source_times[-1].isoformat(),
        "feishu_snapshot_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "records": len(old_fields), "distinct_source_stamps": stamps,
    }, ensure_ascii=False), flush=True)
    views = validate_views(root, token, field_id)
    changes = plan_changes(old)
    max_changed = guard_delta_size(changes, len(old))
    before = queue.partition(old_fields)
    eligibility_counts = age.stats(old_fields.values())
    print("LEAD_DELTA_PLAN=" + json.dumps({
        "records": len(old), "source_stamps": stamps,
        "pending_updates": len(changes), "allowed_max": max_changed,
        "cutoff_kst": eligibility_counts["cutoff"],
        "eligibility": eligibility_counts["counts"],
        "counts_before": {k: len(v) for k, v in before.items()},
        "apply": apply
    }, ensure_ascii=False), flush=True)

    if not apply:
        if simulate_one:
            scenario = simulate_single_manual_change(old)
            print("LEAD_DELTA_SIMULATED_ONE_CHANGE_PASS=" +
                  json.dumps(scenario, ensure_ascii=False), flush=True)
        print("LEAD_DELTA_READ_ONLY_PASS=1", flush=True)
        return
    if not changes:
        # A no-op is not proven by a single early read. Refetch after the
        # audit, to detect manual edits between initial read and view check.
        current = queue.load_records(root, token)
        validate_prewrite_snapshot(old, current)
        current_fields = {key: rec["fields"] for key, rec in current.items()}
        source_stamps_fresh(current_fields)
        late_changes = plan_changes(current)
        if late_changes:
            raise RuntimeError("LEAD_DELTA_NO_NEW_DATA_INVALIDATED_BY_NEW_CHECKBOX")
        stats = verify_view_ids(root, token, current_fields, views)
        print("LEAD_DELTA_NO_NEW_DATA=1 " + json.dumps({
            "checked": len(current), "views_verified": len(queue.QUEUES),
            "counts": stats, "writes": 0,
            "second_snapshot_verified": True,
        }, ensure_ascii=False), flush=True)
        return
    # Refetch user-owned checkboxes immediately before any write. If a user
    # changed their Lead during this run, abort without writing stale labels.
    latest = queue.load_records(root, token)
    verified_prewrite = validate_prewrite_snapshot(old, latest)
    latest_fields = {key: rec["fields"] for key, rec in latest.items()}
    source_stamps_fresh(latest_fields)
    changes = plan_changes(latest)
    guard_delta_size(changes, len(latest))
    print("LEAD_DELTA_PREWRITE_SNAPSHOT_PASS="+str(verified_prewrite)+
          " pending="+str(len(changes)), flush=True)
    old = latest
    if not changes:
        stats = verify_view_ids(root, token, latest_fields, views)
        print("LEAD_DELTA_NO_NEW_DATA=1 " + json.dumps({
            "checked": len(old), "views_verified": len(queue.QUEUES),
            "counts": stats, "writes": 0,
            "second_snapshot_verified": True,
        }, ensure_ascii=False), flush=True)
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
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--apply", action="store_true")
    options.add_argument("--simulate-one", action="store_true",
                         help="Test one checkbox flip in memory without any Feishu writes")
    arg = parser.parse_args()
    try:
        main(apply=arg.apply, simulate_one=arg.simulate_one)
    except Exception as exc:
        print("LEAD_DELTA_FAILED="+str(exc), file=sys.stderr)
        sys.exit(1)
