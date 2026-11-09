#!/usr/bin/env python3
"""Save the native Feishu sales-home grid sort; no customer/source writes."""
import json
import os
import subprocess
import sys
import time
import urllib.parse

from qq_mail_ingest import SafeError, auth, get_fields, list_all, plain_field
from sales_native_home import (
    EXPECTED_BASE, HOME, CURATED_VIEW, CURATED_ORDER, CURATED_DISPLAY,
    table_map, list_views, target_path, MENUS, presentation, PINNED_KEYS, ARCHIVE_DISPLAY,
)
from setup_sales_web import get_view

SORT_FIELD = "표시순서"
EXPECTED = {"sort_config": [{"field": SORT_FIELD, "desc": False}]}
# Index column remains first; category is the earliest movable column.
CURATED_COLUMNS=(
    "Menu Key", "메뉴 구분", "화면", "바로가기",
    "데이터 상태", "업무 내용", "갱신 시각",
)
COLUMNS_PAYLOAD={"visible_fields":list(CURATED_COLUMNS)}


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


def visible_items(document):
    if isinstance(document,list):
        return document
    if isinstance(document,dict):
        if isinstance(document.get("visible_fields"),list):
            return document["visible_fields"]
        for key in ("data","result","property"):
            nested=document.get(key)
            if isinstance(nested,(list,dict)):
                values=visible_items(nested)
                if values is not None:
                    return values
    return None


def matches_columns(document, fields):
    values=visible_items(document)
    if values is None:
        return False
    by_id={row.get("field_id"):row.get("field_name") for row in fields}
    names=[]
    for item in values:
        if isinstance(item,str):
            names.append(by_id.get(item,item))
        elif isinstance(item,dict):
            key=item.get("field_id",item.get("field",item.get("name")))
            if not isinstance(key,str):
                return False
            names.append(by_id.get(key,key))
        else:
            return False
    return names==list(CURATED_COLUMNS)


def ensure_column_order(base, table_id, view_id, fields,mode):
    all_names={f.get("field_name") for f in fields}
    if not set(CURATED_COLUMNS).issubset(all_names):
        raise SafeError("PORTAL_COLUMNS_REQUIRED_FIELD_MISSING")
    link=next(f for f in fields if f.get("field_name")=="바로가기")
    if link.get("type")!=15:
        raise SafeError("PORTAL_COLUMNS_HYPERLINK_TYPE_MISMATCH")
    before=run_cli("+view-get-visible-fields",base,table_id,view_id)
    already=matches_columns(before,fields)
    if mode=="plan":
        print("PORTAL_COLUMNS_PLAN configured="+str(already)+" writes=0")
        return
    if not already:
        run_cli("+view-set-visible-fields",base,table_id,view_id,COLUMNS_PAYLOAD)
    after=run_cli("+view-get-visible-fields",base,table_id,view_id)
    if not matches_columns(after,fields):
        raise SafeError("PORTAL_COLUMNS_READBACK_MISMATCH")
    print("PORTAL_COLUMNS_PASS second=category fourth=direct_link "
          "visible=7 changed="+str(int(not already)))


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


def numeric_rank(value):
    if isinstance(value, list) and len(value) == 1:
        return numeric_rank(value[0])
    if isinstance(value, dict):
        return numeric_rank(value.get("value", value.get("text")))
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        if number.is_integer() and 0 <= number <= 9999:
            return int(number)
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def verify_view_rows(token, table_path, view_id):
    """Audit stored menu rows independently from the native saved sort metadata.

    The Feishu view-scoped records API has repeatedly timed out even with a
    12-row view. Reading the small home table directly avoids that endpoint.
    The view filter and saved sort are validated separately in main().
    """
    del view_id
    records = list_all(table_path + "/records", token, "portal_sort_home_rows")
    expected = {}
    for source_index, menu in enumerate(MENUS, 1):
        key, _, title, *_ = menu
        rank, label, color = presentation(key, title, source_index)
        expected[key] = {
            "rank": rank, "label": label, "color": color,
            "display": CURATED_DISPLAY if key in PINNED_KEYS else ARCHIVE_DISPLAY,
        }
    indexed = {}
    for record in records:
        fields = record.get("fields") or {}
        key = plain_field(fields.get("Menu Key")).strip()
        if not key or key in indexed:
            raise SafeError("PORTAL_SORT_DUPLICATE_OR_EMPTY_KEY")
        indexed[key] = fields
    if set(indexed) != set(expected) or len(records) != len(expected):
        raise SafeError("PORTAL_SORT_SOURCE_MEMBERSHIP_MISMATCH")
    issues = []
    for key, rule in expected.items():
        fields = indexed[key]
        got = {
            "rank": numeric_rank(fields.get(SORT_FIELD)),
            "label": plain_field(fields.get("화면")).strip(),
            "color": plain_field(fields.get("메뉴 구분")).strip(),
            "display": plain_field(fields.get("표시")).strip(),
        }
        if got != rule:
            issues.append(key)
        raw_url=plain_field(fields.get("바로가기 URL")).strip()
        link=fields.get("바로가기")
        if isinstance(link,list) and len(link)==1:
            link=link[0]
        expected_link={"text":"열기","link":raw_url} if raw_url else None
        if (raw_url and not (raw_url.startswith("https://ocnz4cb25scn.feishu.cn/base/")
                             and "?table=" in raw_url and "&view=" in raw_url)):
            issues.append(key)
        elif (link or None)!=expected_link:
            issues.append(key)
    if issues:
        # Only menu route keys, never customer data, enter the audit log.
        print("PORTAL_SORT_SOURCE_DIFFERENCES=" + ",".join(issues))
        raise SafeError("PORTAL_SORT_RECORD_READBACK_MISMATCH")
    print("PORTAL_SORT_SOURCE_PASS total=" + str(len(expected))
          + " curated=" + str(len(PINNED_KEYS))
          + " managed=" + str(len(expected) - len(PINNED_KEYS))
          + " priorities=01_to_12 colors=verified")
    return True


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
        ensure_column_order(EXPECTED_BASE, table_id, view_id, fields,mode)
        return
    changed = not sort_matches(current, sort_field["field_id"])
    if changed:
        run_cli("+view-set-sort", EXPECTED_BASE, table_id, view_id, EXPECTED)
    actual = run_cli("+view-get-sort", EXPECTED_BASE, table_id, view_id)
    if not sort_matches(actual, sort_field["field_id"]):
        raise SafeError("PORTAL_SORT_CONFIG_READBACK_MISMATCH")
    print("PORTAL_SORT_CONFIG_PASS field=display_order ascending=true changed="
          + str(int(changed)))
    ensure_column_order(EXPECTED_BASE, table_id, view_id, fields,mode)
    record_state = "PASS"
    try:
        verify_view_rows(token, path, view_id)
    except SafeError as exc:
        # A transient records API outage must not erase a proven persisted
        # view-sort configuration. Keep this partial audit explicitly visible.
        if str(exc).endswith("_NETWORK_ERROR"):
            record_state = "SOURCE_UNAVAILABLE"
            print("PORTAL_SORT_SOURCE_VERIFY_SOURCE_UNAVAILABLE")
        else:
            raise
    print("PORTAL_SORT_APPLY_PASS sort_config=PASS record_check="
          + record_state + " records_deleted=0 source_table_writes=0")


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
