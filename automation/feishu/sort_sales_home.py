#!/usr/bin/env python3
"""Save the native Feishu sales-home grid sort; no customer/source writes."""
import json
import os
import subprocess
import sys
import time
import urllib.parse

from qq_mail_ingest import SafeError, api, auth, get_fields, plain_field
from sales_native_home import (
    EXPECTED_BASE, HOME, CURATED_VIEW, CURATED_ORDER, CURATED_DISPLAY,
    table_map, list_views, target_path,
)
from setup_sales_web import get_view

SORT_FIELD = "표시순서"
EXPECTED = {"sort_config": [{"field": SORT_FIELD, "desc": False}]}


def get_sort_items(document):
    """CLI versions may return the sort_config directly or wrapped in data."""
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        if isinstance(document.get("sort_config"), list):
            return document["sort_config"]
        for key in ("data", "sort", "property", "result"):
            nested = document.get(key)
            if isinstance(nested, (dict, list)):
                items = get_sort_items(nested)
                if items is not None:
                    return items
    return None


def sort_matches(document, field_id):
    items = get_sort_items(document)
    if not isinstance(items, list) or len(items) != 1:
        return False
    entry = items[0]
    return (isinstance(entry, dict)
            and entry.get("field", entry.get("field_id")) in (SORT_FIELD, field_id)
            and entry.get("desc") is False)


def run_cli(action, base, table_id, view_id, config=None):
    argv = [
        "lark-cli", "base", action, "--base-token", base,
        "--table-id", table_id, "--view-id", view_id,
        "--as", "bot", "--format", "json",
    ]
    if config is not None:
        argv.extend(["--json", json.dumps(config, ensure_ascii=False)])
    result = subprocess.run(argv, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise SafeError("PORTAL_SORT_CLI_FAILED_" + action.replace("+", "").upper())
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        raise SafeError("PORTAL_SORT_CLI_BAD_JSON") from None


def verify_filtered_view(view, field_id):
    if view.get("view_name") != CURATED_VIEW or view.get("view_type") != "grid":
        raise SafeError("PORTAL_SORT_WRONG_VIEW")
    properties = view.get("property") or {}
    filt = properties.get("filter_info") or {}
    conditions = filt.get("conditions") or []
    if filt.get("conjunction") != "and" or len(conditions) != 1:
        raise SafeError("PORTAL_SORT_FILTER_UNVERIFIED")
    condition = conditions[0]
    try:
        values = json.loads(condition.get("value") or "null")
    except (ValueError, TypeError):
        raise SafeError("PORTAL_SORT_FILTER_INVALID") from None
    if (condition.get("field_id") != field_id
            or condition.get("operator") != "is"
            or values != [CURATED_DISPLAY]):
        raise SafeError("PORTAL_SORT_FILTER_MISMATCH")


def verify_view_rows(token, table_path, view_id):
    url = (table_path + "/records?page_size=100&view_id="
           + urllib.parse.quote(view_id, safe=""))
    last = None
    for i in range(4):
        data = api("GET", url, token, action="portal_sorted_records")
        rows = data.get("items") or []
        keys = [plain_field((r.get("fields") or {}).get("Menu Key")).strip()
                for r in rows]
        positions = [(r.get("fields") or {}).get(SORT_FIELD) for r in rows]
        # Feishu v1 list(view_id=...) may return backend record order even when
        # the native Base v3 grid has a saved sort. Verify membership and ranks
        # here, and independently verify the persisted grid sort via v3 GET.
        expected = {key: rank for rank, key in enumerate(CURATED_ORDER, 1)}
        actual = dict(zip(keys, positions))
        if (not data.get("has_more") and len(rows) == len(expected)
                and len(set(keys)) == len(expected) and actual == expected):
            print("PORTAL_SORT_RECORD_MEMBERSHIP_PASS rows=12 assignments=12"
                  + " api_return_sorted=" + str(keys == list(CURATED_ORDER)))
            return True
        last = (len(rows), len(set(keys)), data.get("has_more"))
        if i < 3:
            time.sleep(2)
    # Only metadata is logged, never customer records.
    print("PORTAL_SORT_RECORD_ORDER_UNVERIFIED rows=%s unique=%s paged=%s" % last)
    raise SafeError("PORTAL_SORT_RECORD_READBACK_MISMATCH")


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PORTAL_SORT_REFUSE_NON_SALES_BASE")
    mode = os.environ.get("FEISHU_PORTAL_MODE", "plan")
    if mode not in ("plan", "apply"):
        raise SafeError("PORTAL_SORT_UNKNOWN_MODE")
    token, root = auth()
    tables = table_map(token, root)
    table_id = tables.get(HOME)
    if not table_id:
        raise SafeError("PORTAL_SORT_HOME_MISSING")
    path = target_path(root, table_id)
    views = list_views(token, path)
    view_id = views.get(CURATED_VIEW)
    if not view_id:
        raise SafeError("PORTAL_SORT_VIEW_MISSING")
    fields = get_fields(token, path)
    field_by_name = {field.get("field_name"):field for field in fields}
    sort_field = field_by_name.get(SORT_FIELD) or {}
    display_field = field_by_name.get("표시") or {}
    if sort_field.get("type") != 2 or not sort_field.get("field_id"):
        raise SafeError("PORTAL_SORT_NUMBER_FIELD_MISSING")
    if display_field.get("type") != 1 or not display_field.get("field_id"):
        raise SafeError("PORTAL_SORT_DISPLAY_FIELD_MISSING")
    verify_filtered_view(get_view(token, path, view_id), display_field["field_id"])
    current = run_cli("+view-get-sort", EXPECTED_BASE, table_id, view_id)
    if mode == "plan":
        print("PORTAL_SORT_PLAN_PASS configured="
              + str(sort_matches(current, sort_field["field_id"])) + " writes=0")
        return
    changed = not sort_matches(current, sort_field["field_id"])
    if changed:
        run_cli("+view-set-sort", EXPECTED_BASE, table_id, view_id, EXPECTED)
    actual = run_cli("+view-get-sort", EXPECTED_BASE, table_id, view_id)
    if not sort_matches(actual, sort_field["field_id"]):
        raise SafeError("PORTAL_SORT_CONFIG_READBACK_MISMATCH")
    print("PORTAL_SORT_CONFIG_PASS field=display_order ascending=true changed="
          + str(int(changed)))
    verify_view_rows(token, path, view_id)
    print("PORTAL_SORT_APPLY_PASS records_deleted=0 source_table_writes=0")


if __name__ == "__main__":
    try:
        main()
    except (SafeError, subprocess.TimeoutExpired) as exc:
        reason = str(exc) if isinstance(exc, SafeError) else "PORTAL_SORT_CLI_TIMEOUT"
        print("PORTAL_SORT_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print("PORTAL_SORT_FAILED:" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
