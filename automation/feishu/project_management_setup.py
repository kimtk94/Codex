#!/usr/bin/env python3
"""Add missing manual-management fields; inspect views without editing them.

Only the existing Project Progress Board is eligible. No record endpoint is
read or written, no person/date default is assigned, and existing field or view
settings are never rewritten. Kanban grouping, calendar binding, and date
filters remain UI-managed: the public view model does not expose enough data
to certify those settings here.
"""
import argparse
import copy
import json
import os
import re
import sys
import urllib.parse

from qq_mail_ingest import SafeError, api, auth
from setup_sales_web import EXPECTED_BASE


TABLE_NAME = "Project Progress Board"
TABLE_ID = "tblTZe5tkRUeOHM8"
ROOT = "/open-apis/bitable/v1/apps/" + EXPECTED_BASE
TABLE_PATH = ROOT + "/tables/" + TABLE_ID
MANUAL_FIELDS = (
    {"field_name": "관리 담당", "type": 11, "property": {"multiple": False}},
    {"field_name": "관리 우선순위", "type": 3, "property": {"options": [
        {"name": name} for name in ("긴급", "높음", "보통", "낮음")]}},
    {"field_name": "관리 상태", "type": 3, "property": {"options": [
        {"name": name} for name in ("미착수", "진행 중", "대기", "확인 완료")]}},
    {"field_name": "다음 확인일", "type": 5, "property": {"auto_fill": False}},
    {"field_name": "관리 메모", "type": 1},
)
VIEW_TYPES = {
    "00 관리 작업대": "grid",
    "01 오늘 확인": "grid",
    "02 관리 칸반": "kanban",
    "03 확인 일정": "calendar",
}
# Preserve the UI-confirmed identities; a same-name replacement is not the
# reviewed view. Missing views are reported, never created by this helper.
VIEW_IDS = {
    "00 관리 작업대": "vewsBMUPG6",
    "01 오늘 확인": "vewB79tmDj",
    "02 관리 칸반": "vewp5jdx1d",
    "03 확인 일정": "vewmYMuKkO",
}
FIELD_SPECS = {item["field_name"]: item for item in MANUAL_FIELDS}


class MetadataClient:
    """Allowlisted metadata transport; only exact manual field creates may write."""
    def __init__(self, token, root=ROOT, request=api):
        if root != ROOT:
            raise SafeError("PROJECT_MANAGEMENT_UNKNOWN_BASE")
        self.token = token
        self.request = request

    def call(self, method, path, data=None):
        parsed = urllib.parse.urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise SafeError("PROJECT_MANAGEMENT_UNSAFE_PATH")
        allowed_reads = {ROOT + "/tables", TABLE_PATH + "/fields", TABLE_PATH + "/views"}
        view_detail = re.fullmatch(re.escape(TABLE_PATH) + r"/views/vew[A-Za-z0-9]+", parsed.path)
        if method == "GET":
            if data is not None or (parsed.path not in allowed_reads and not view_detail):
                raise SafeError("PROJECT_MANAGEMENT_READ_OUTSIDE_METADATA")
        elif method == "POST":
            if parsed.path != TABLE_PATH + "/fields" or parsed.query:
                raise SafeError("PROJECT_MANAGEMENT_WRITE_OUTSIDE_FIELDS")
            if not isinstance(data, dict) or data != FIELD_SPECS.get(data.get("field_name")):
                raise SafeError("PROJECT_MANAGEMENT_UNAPPROVED_FIELD_CREATE")
        else:
            raise SafeError("PROJECT_MANAGEMENT_MUTATION_FORBIDDEN")
        return self.request(method, path, self.token, data=data,
                            action="project_management_metadata")

    def listing(self, resource):
        path = ROOT + "/tables" if resource == "tables" else TABLE_PATH + "/" + resource
        rows = []
        cursor = ""
        seen = set()
        for _ in range(100):
            query = {"page_size": 100}
            if cursor:
                query["page_token"] = cursor
            page = self.call("GET", path + "?" + urllib.parse.urlencode(query))
            items = page.get("items")
            if not isinstance(items, list):
                raise SafeError("PROJECT_MANAGEMENT_METADATA_ITEMS_MISSING")
            rows.extend(items)
            if not page.get("has_more"):
                return rows
            cursor = page.get("page_token")
            if not isinstance(cursor, str) or not cursor or cursor in seen:
                raise SafeError("PROJECT_MANAGEMENT_BAD_PAGINATION")
            seen.add(cursor)
        raise SafeError("PROJECT_MANAGEMENT_PAGINATION_LIMIT")


def resolve_table(items):
    names = [item for item in items if item.get("name") == TABLE_NAME]
    identities = [item for item in items if item.get("table_id") == TABLE_ID]
    if len(names) != 1 or len(identities) != 1:
        raise SafeError("PROJECT_MANAGEMENT_TABLE_NOT_UNIQUE")
    if names[0].get("table_id") != TABLE_ID or identities[0].get("name") != TABLE_NAME:
        raise SafeError("PROJECT_MANAGEMENT_TABLE_ID_NAME_MISMATCH")


def inspect_fields(items):
    by_name = {}
    for item in items:
        name = item.get("field_name")
        if name not in FIELD_SPECS:
            continue
        if name in by_name or not item.get("field_id"):
            raise SafeError("PROJECT_MANAGEMENT_FIELD_NOT_UNIQUE:" + name)
        if item.get("type") != FIELD_SPECS[name]["type"]:
            raise SafeError("PROJECT_MANAGEMENT_FIELD_TYPE_MISMATCH:" + name)
        by_name[name] = item
    missing = [item["field_name"] for item in MANUAL_FIELDS if item["field_name"] not in by_name]
    notes = []
    for name, field in by_name.items():
        actual = field.get("property") or {}
        expected = FIELD_SPECS[name].get("property") or {}
        for key, value in expected.items():
            if key == "options":
                options = actual.get("options")
                found = {item.get("name") for item in options if isinstance(item, dict)} if isinstance(options, list) else set()
                if found != {item["name"] for item in value} or not isinstance(options, list) or len(options) != len(value):
                    notes.append({"field": name, "setting": key, "status": "UI_REVIEW_REQUIRED"})
            elif actual.get(key) is not value:
                notes.append({"field": name, "setting": key, "status": "UI_REVIEW_REQUIRED"})
    return by_name, missing, notes


def inspect_views(client, items, *, allow_calendar_review=False):
    found = {}
    names_by_id = {identity: name for name, identity in VIEW_IDS.items()}
    for item in items:
        name = item.get("view_name")
        identity = item.get("view_id")
        if identity in names_by_id and names_by_id[identity] != name:
            raise SafeError("PROJECT_MANAGEMENT_VIEW_ID_NAME_MISMATCH")
        if name not in VIEW_TYPES:
            continue
        if name in found or not re.fullmatch(r"vew[A-Za-z0-9]+", item.get("view_id") or ""):
            raise SafeError("PROJECT_MANAGEMENT_VIEW_NOT_UNIQUE:" + name)
        if identity != VIEW_IDS[name]:
            raise SafeError("PROJECT_MANAGEMENT_VIEW_ID_MISMATCH:" + name)
        detail = item
        if not detail.get("view_type"):
            detail = client.call("GET", TABLE_PATH + "/views/" + item["view_id"]).get("view") or {}
            if detail.get("view_id") != item["view_id"] or detail.get("view_name") != name:
                raise SafeError("PROJECT_MANAGEMENT_VIEW_READBACK_MISMATCH:" + name)
        actual_type = detail.get("view_type")
        if actual_type != VIEW_TYPES[name]:
            # The UI supports calendar views, but the public metadata API may
            # not expose a calendar enum. Never assume a mismatching type is
            # a valid calendar. Only the exact reviewed calendar identity
            # can be reported as unresolved in the read-only plan.
            if not (allow_calendar_review and name == "03 확인 일정"):
                raise SafeError("PROJECT_MANAGEMENT_VIEW_TYPE_MISMATCH:" + name)
            reported_type = actual_type
            if not isinstance(actual_type, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", actual_type):
                reported_type = "UNREPORTED" if actual_type is None or actual_type == "" else "UNRECOGNIZED"
            found[name] = {"view_id": identity, "view_type": reported_type,
                           "expected_view_type": VIEW_TYPES[name],
                           "type_status": "UI_REVIEW_REQUIRED"}
        else:
            found[name] = {"view_id": identity, "view_type": actual_type,
                           "type_status": "MATCH"}
    return found, [name for name in VIEW_TYPES if name not in found]


def setup(client, mode="plan"):
    if mode not in {"plan", "apply"}:
        raise SafeError("PROJECT_MANAGEMENT_INVALID_MODE")
    resolve_table(client.listing("tables"))
    original_fields = client.listing("fields")
    existing, missing, notes = inspect_fields(original_fields)
    original_views = client.listing("views")
    views, missing_views = inspect_views(client, original_views, allow_calendar_review=(mode == "plan"))
    planned = list(missing)
    created = []
    if mode == "apply":
        for name in planned:
            # Re-read immediately before each create so a concurrent UI add is
            # reused, never patched, converted, or duplicated by this helper.
            current, _, _ = inspect_fields(client.listing("fields"))
            if name in current:
                continue
            client.call("POST", TABLE_PATH + "/fields", copy.deepcopy(FIELD_SPECS[name]))
            current, _, _ = inspect_fields(client.listing("fields"))
            if name not in current:
                raise SafeError("PROJECT_MANAGEMENT_FIELD_CREATE_READBACK_MISSING:" + name)
            created.append(name)
        after_fields = client.listing("fields")
        existing, missing, notes = inspect_fields(after_fields)
        if missing:
            raise SafeError("PROJECT_MANAGEMENT_FIELDS_INCOMPLETE")
        before_ids = {item.get("field_id"): (item.get("field_name"), item.get("type")) for item in original_fields}
        after_ids = {item.get("field_id"): (item.get("field_name"), item.get("type")) for item in after_fields}
        if any(after_ids.get(identity) != value for identity, value in before_ids.items()):
            raise SafeError("PROJECT_MANAGEMENT_EXISTING_FIELD_IDENTITY_CHANGED")
        after_views = client.listing("views")
        before_view_ids = {item.get("view_id"): item.get("view_name") for item in original_views}
        after_view_ids = {item.get("view_id"): item.get("view_name") for item in after_views}
        if any(after_view_ids.get(identity) != name for identity, name in before_view_ids.items()):
            raise SafeError("PROJECT_MANAGEMENT_EXISTING_VIEW_IDENTITY_CHANGED")
        views, missing_views = inspect_views(client, after_views)
    type_review = [name for name, view in views.items()
                   if view["type_status"] == "UI_REVIEW_REQUIRED"]
    return {
        "mode": mode,
        "table_id": TABLE_ID,
        "table_name": TABLE_NAME,
        "field_type_status": "READY" if not missing else "MISSING_FIELDS",
        "planned_field_creates": planned,
        "created_fields": created,
        "field_configuration_review": notes,
        "views": views,
        "missing_ui_views": missing_views,
        "view_presence_status": "PRESENT" if not missing_views else "UI_SETUP_REQUIRED",
        "view_type_status": "UI_REVIEW_REQUIRED" if type_review else ("MISSING_VIEWS" if missing_views else "MATCH"),
        "view_type_review": type_review,
        "view_layout_status": "UI_MANAGED_NOT_VERIFIED",
        "ui_checks": ["01 오늘 확인: date filter", "02 관리 칸반: group by 관리 상태", "03 확인 일정: date field 다음 확인일"],
        "record_reads": 0,
        "record_writes": 0,
        "view_writes": 0,
        "existing_field_updates": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "apply"), default="plan")
    args = parser.parse_args(argv)
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PROJECT_MANAGEMENT_UNKNOWN_BASE")
    token, root = auth()
    result = setup(MetadataClient(token, root), args.mode)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## Project management metadata\n\n")
            stream.write("- Mode: " + args.mode + "\n")
            stream.write("- Field types: " + result["field_type_status"] + "\n")
            stream.write("- Missing fields planned: " + str(len(result["planned_field_creates"])) + "\n")
            stream.write("- Fields created: " + str(len(result["created_fields"])) + "\n")
            stream.write("- View presence: " + result["view_presence_status"] + "\n")
            stream.write("- View types: " + result["view_type_status"] + "\n")
            stream.write("- View types requiring UI review: " + str(len(result["view_type_review"])) + "\n")
            stream.write("- Existing field settings requiring UI review: " + str(len(result["field_configuration_review"])) + "\n")
            stream.write("- Kanban grouping, calendar binding and the date filter require UI verification.\n")
            stream.write("- No records, existing field settings, or views were modified.\n")
    return result


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("PROJECT_MANAGEMENT_SETUP_FAILED:" + reason, file=sys.stderr)
        raise SystemExit(1)
