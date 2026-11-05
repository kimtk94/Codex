#!/usr/bin/env python3
"""Idempotent Feishu Base native-web view setup for the NEW sales workspace.

Uses ONLY FEISHU_SALES_BASE_APP_TOKEN, never the original business Feishu Base.
Creates non-destructive Grid views; customer records remain untouched.
Filtered views are initially named '설정중' and renamed only after filter patch.
"""
import json
import os
import sys
import time
import urllib.parse

from qq_mail_ingest import auth, api, get_fields, list_all, SafeError

EXPECTED_BASE = "IpMkbUD0vaFqtYs93a3csXtdn1b"
BASE_URL = "https://ocnz4cb25scn.feishu.cn/base/" + EXPECTED_BASE

# Only names, no customer values.
VIEWS = {
    "QQ Mail Intake": (("전체 메일", None), ("수신 메일", "INBOUND"),
                       ("발신 메일", "OUTBOUND")),
    "Accounts": (("기관별 고객", None),),
    "Contacts": (("한글 고객 검색", None),),
    "Opportunities": (("영업 기회", None),),
    "Quotes": (("견적 관리", None),),
    "Projects": (("프로젝트 현황", None),),
    "Revenue": (("월별 매출", None),),
}


def find_tables(token, root):
    tables = list_all(root + "/tables", token, "sales_web_list_tables")
    by_name = {}
    for row in tables:
        name, table_id = row.get("name"), row.get("table_id")
        if name in by_name or not name or not table_id:
            raise SafeError("DUPLICATE_OR_EMPTY_TABLE_METADATA")
        by_name[name] = table_id
    if any(name not in by_name for name in VIEWS):
        raise SafeError("SALES_WEB_REQUIRED_TABLES_MISSING")
    return by_name


def list_views(token, table_path):
    rows = list_all(table_path + "/views", token, "sales_web_list_views")
    names = {}
    for item in rows:
        name = item.get("view_name")
        vid = item.get("view_id")
        if not name or not vid or name in names:
            raise SafeError("DUPLICATE_OR_EMPTY_VIEW_METADATA")
        names[name] = vid
    return names


def resolve_view(token, table_path, title, filtered):
    names = list_views(token, table_path)
    pending_name = "설정중_" + title if filtered else title
    if title in names:
        return names[title], False
    if pending_name in names:
        return names[pending_name], False
    created = api("POST", table_path + "/views", token,
                  data={"view_name": pending_name, "view_type": "grid"},
                  action="sales_web_view_create")
    item = created.get("view") or {}
    view_id = item.get("view_id")
    if not view_id:
        # Different Feishu API versions may return a shallow body. Verify by listing.
        names = list_views(token, table_path)
        view_id = names.get(pending_name)
    if not view_id:
        raise SafeError("VIEW_CREATE_NOT_VERIFIED")
    print("VIEW_CREATED=" + title)
    return view_id, True


def get_view(token, table_path, view_id):
    payload = api("GET", table_path + "/views/" + urllib.parse.quote(view_id, safe=""),
                  token, action="sales_web_view_readback")
    return payload.get("view") or {}


def field_map(token, table_path):
    rows = get_fields(token, table_path)
    return {r.get("field_name"): r.get("field_id") for r in rows}


def filter_matches(view, field_id, expected):
    info = ((view.get("property") or {}).get("filter_info") or {})
    conditions = info.get("conditions") or []
    if len(conditions) != 1 or info.get("conjunction") != "and":
        return False
    condition = conditions[0]
    try:
        values = json.loads(condition.get("value") or "null")
    except (ValueError, TypeError):
        return False
    return (condition.get("field_id") == field_id
            and condition.get("operator") == "is"
            and values == [expected])


def ensure_view(token, table_path, title, filter_value=None):
    view_id, created = resolve_view(token, table_path, title, bool(filter_value))
    if not filter_value:
        view = get_view(token, table_path, view_id)
        if view.get("view_name") != title:
            raise SafeError("PLAIN_VIEW_READBACK_MISMATCH")
        return view_id
    fields = field_map(token, table_path)
    direction_id = fields.get("Direction")
    if not direction_id:
        raise SafeError("DIRECTION_FIELD_MISSING")
    view = get_view(token, table_path, view_id)
    if view.get("view_name") == title and filter_matches(view, direction_id, filter_value):
        return view_id
    # Patch filter AND final title atomically, preventing unfiltered views from
    # being misleadingly labelled "수신 메일" or "발신 메일".
    api("PATCH", table_path + "/views/" + urllib.parse.quote(view_id, safe=""),
        token, data={
            "view_name": title,
            "property": {"filter_info": {"conjunction": "and", "conditions": [{
                "field_id": direction_id, "operator": "is",
                "value": json.dumps([filter_value], ensure_ascii=False),
            }]}}
        }, action="sales_web_view_filter_patch")
    # Feishu can be eventually consistent after a newly-created view.
    for attempt in range(3):
        updated = get_view(token, table_path, view_id)
        if updated.get("view_name") == title and filter_matches(updated, direction_id, filter_value):
            print("VIEW_FILTER_VERIFIED=" + title)
            return view_id
        if attempt < 2:
            time.sleep(1.5)
    raise SafeError("FILTER_READBACK_MISMATCH_" + filter_value)


def main():
    if os.environ.get("FEISHU_SALES_BASE_APP_TOKEN", "") != EXPECTED_BASE:
        raise SafeError("REFUSE_UNRECOGNIZED_FEISHU_BASE")
    mode = os.environ.get("FEISHU_WEB_MODE", "plan")
    if mode not in ("plan", "apply"):
        raise SafeError("UNKNOWN_WEB_MODE")
    token, root = auth()
    tables = find_tables(token, root)
    print("SALES_WEB_BASE_ACCESS_PASS tables=" + str(len(tables)))
    count = 0
    for table_name, specs in VIEWS.items():
        table_id = tables[table_name]
        path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
        existing = list_views(token, path)
        print("WEB_TABLE=" + table_name + " EXISTING_VIEWS=" + str(len(existing)))
        if mode == "plan":
            continue
        for title, direction in specs:
            view_id = ensure_view(token, path, title, direction)
            deep_link = (BASE_URL + "?table=" + urllib.parse.quote(table_id, safe="") +
                         "&view=" + urllib.parse.quote(view_id, safe=""))
            print("WEB_VIEW_READY=" + title + " URL=" + deep_link)
            count += 1
            time.sleep(0.5)
    print("SALES_WEB_SETUP_PASS mode=" + mode + " configured_views=" + str(count)
          + " business_record_writes=0")


if __name__ == "__main__":
    try:
        main()
    except SafeError as exc:
        print("SALES_WEB_SETUP_FAILED:" + str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("SALES_WEB_SETUP_FAILED:" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
