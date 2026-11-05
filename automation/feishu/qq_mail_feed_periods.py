#!/usr/bin/env python3
"""Feishu QQ Mail Intake: chronological CURRENT/HISTORY feed, 2026 scope.

Source of truth is the email Received At header, NOT the Feishu ingest timestamp.
The separate Imported KST column lets users see late-arriving historical backfills.
This script never reads Google Sheets, removes records, or classifies revenue.
"""
import datetime as dt
import os
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

from qq_mail_ingest import SafeError, api, auth, find_table, get_fields, list_all, plain_field, SMOKE_KEY
from setup_sales_web import BASE_URL, EXPECTED_BASE, filter_matches, get_view, list_views, resolve_view, field_map

KST = ZoneInfo("Asia/Seoul")
YEAR_START = dt.datetime(2026, 1, 1, tzinfo=KST)
FIELDS = {
    "Feed Lane": 1,
    "Received KST": 1,
    "Imported KST": 1,
}
VIEWS = (
    ("현재 메일 · 최근 30일", "CURRENT_30D"),
    ("과거 메일 · 2026", "HISTORY_2026"),
    ("메일 날짜 확인 필요", "DATE_REVIEW"),
    ("2026 이전 · 집계 제외", "PRE_2026"),
)
MAX_BATCH = 25


def parse_aware(value):
    value = plain_field(value).strip()
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError):
        return None
    return parsed.astimezone(KST) if parsed.tzinfo else None


def segment(received_at, now, recent_days=30):
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise SafeError("FEED_NOW_MUST_BE_TIMEZONE_AWARE")
    if not isinstance(recent_days, int) or recent_days < 1 or recent_days > 365:
        raise SafeError("INVALID_RECENT_DAYS")
    mail_date = parse_aware(received_at)
    current = now.astimezone(KST)
    if mail_date is None or mail_date > current + dt.timedelta(days=1):
        return "DATE_REVIEW"
    if mail_date < YEAR_START:
        return "PRE_2026"
    if mail_date >= current - dt.timedelta(days=recent_days):
        return "CURRENT_30D"
    return "HISTORY_2026"


def format_kst(value):
    date = parse_aware(value)
    return date.strftime("%Y-%m-%d %H:%M:%S") if date is not None else ""


def changes(record, now, recent_days):
    fields = record.get("fields") or {}
    key = plain_field(fields.get("Mail Key")).strip()
    if key == SMOKE_KEY:
        return {}
    if not key or not record.get("record_id"):
        raise SafeError("FEED_INVALID_RECORD_ID_OR_MAIL_KEY")
    desired = {
        "Feed Lane": segment(fields.get("Received At"), now, recent_days),
        "Received KST": format_kst(fields.get("Received At")),
        "Imported KST": format_kst(fields.get("Captured UTC")),
    }
    return {k: v for k, v in desired.items() if plain_field(fields.get(k)) != v}


def batches(rows, size=MAX_BATCH):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def ensure_fields(token, path):
    types = {field.get("field_name"): field.get("type") for field in get_fields(token, path)}
    for name, kind in FIELDS.items():
        if name in types:
            if types[name] != kind:
                raise SafeError("FEED_FIELD_SCHEMA_CONFLICT")
            continue
        api("POST", path + "/fields", token,
            data={"field_name": name, "type": kind}, action="feed_add_field")
        print("FEED_FIELD_CREATED=" + name)
    check = {f.get("field_name"): f.get("type") for f in get_fields(token, path)}
    if any(check.get(k) != t for k, t in FIELDS.items()):
        raise SafeError("FEED_FIELD_READBACK_FAILED")


def ensure_views(token, path, table_id):
    field_id = field_map(token, path).get("Feed Lane")
    if not field_id:
        raise SafeError("FEED_LANE_FIELD_ID_MISSING")
    for name, lane in VIEWS:
        view_id, _ = resolve_view(token, path, name, True)
        view = get_view(token, path, view_id)
        if not (view.get("view_name") == name and filter_matches(view, field_id, lane)):
            import json
            api("PATCH", path + "/views/" + urllib.parse.quote(view_id, safe=""),
                token, data={
                    "view_name": name,
                    "property": {
                        "filter_info": {
                            "conjunction": "and",
                            "conditions": [{
                                "field_id": field_id,
                                "operator": "is",
                                "value": json.dumps([lane]),
                            }],
                        }
                    }
                }, action="feed_view_patch")
            for attempt in range(4):
                view = get_view(token, path, view_id)
                if view.get("view_name") == name and filter_matches(view, field_id, lane):
                    break
                if attempt < 3:
                    time.sleep(1)
            else:
                raise SafeError("FEED_FILTER_READBACK_MISMATCH")
        url = (BASE_URL + "?table=" + urllib.parse.quote(table_id, safe="") +
               "&view=" + urllib.parse.quote(view_id, safe=""))
        print("FEED_VIEW_READY=" + name + " URL=" + url)


def compute_updates(records, now, recent_days):
    seen = set()
    updates = []
    counts = {"CURRENT_30D": 0, "HISTORY_2026": 0, "DATE_REVIEW": 0, "PRE_2026": 0}
    for record in records:
        key = plain_field((record.get("fields") or {}).get("Mail Key")).strip()
        if key in seen:
            raise SafeError("DUPLICATE_FEED_MAIL_KEY")
        seen.add(key)
        if key == SMOKE_KEY:
            continue
        desired = segment((record.get("fields") or {}).get("Received At"), now, recent_days)
        counts[desired] += 1
        update = changes(record, now, recent_days)
        if update:
            updates.append({"record_id": record["record_id"], "fields": update})
    return updates, counts


def apply_updates(token, path, updates, limit):
    updated = 0
    for batch in batches(updates[:limit]):
        data = api("POST", path + "/records/batch_update", token,
                   data={"records": batch}, action="feed_batch_update")
        ids = {r.get("record_id") for r in (data.get("records") or [])}
        if ids != {r["record_id"] for r in batch}:
            raise SafeError("FEED_BATCH_RESULT_UNVERIFIED")
        updated += len(batch)
        time.sleep(0.25)
    return updated


def verify(token, path, target):
    if not target:
        return
    records = list_all(path + "/records", token, "feed_post_write_readback")
    index = {r.get("record_id"): r for r in records}
    for row in target:
        existing = index.get(row["record_id"])
        if not existing:
            raise SafeError("FEED_READBACK_MISSING_RECORD")
        for key, expected in row["fields"].items():
            if plain_field((existing.get("fields") or {}).get(key)) != expected:
                raise SafeError("FEED_READBACK_VALUE_MISMATCH")


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN", "").strip() != EXPECTED_BASE:
        raise SafeError("REFUSE_UNRELATED_FEISHU_BASE")
    mode = os.environ.get("FEISHU_FEED_MODE", "plan").lower().strip()
    if mode not in ("plan", "apply"):
        raise SafeError("INVALID_FEED_MODE")
    recent_days = int(os.environ.get("FEISHU_CURRENT_MAIL_DAYS", "30"))
    limit = min(max(1, int(os.environ.get("FEISHU_FEED_MAX_UPDATES", "1500"))), 3000)
    now = dt.datetime.now(KST)
    token, root = auth()
    table_id = find_table(token, root)
    if not table_id:
        raise SafeError("MAIL_INTAKE_TABLE_MISSING")
    path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
    records = list_all(path + "/records", token, "feed_read_all")
    updates, counts = compute_updates(records, now, recent_days)
    print("FEED_SOURCE_ROWS=" + str(sum(counts.values())))
    for lane, count in counts.items():
        print("FEED_SEGMENT_" + lane + "=" + str(count))
    print("FEED_PENDING_UPDATES=" + str(len(updates)))
    if mode == "plan":
        print("FEED_PLAN_PASS writes=0")
        return
    ensure_fields(token, path)
    ensure_views(token, path, table_id)
    updated = apply_updates(token, path, updates, limit)
    verify(token, path, updates[:updated])
    print("FEED_APPLY_PASS updated=" + str(updated) + " remaining=" +
          str(max(0, len(updates) - updated)) +
          " original_mail_edits=0 tax_invoice_changes=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("FEED_REFRESH_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
