#!/usr/bin/env python3
"""Verify or patch six charts in the explicitly owned native overview dashboard.

Native charts read the existing tables directly. This owner only reconciles
their aggregation and scope; it never writes records, creates/deletes blocks,
or changes positions, colors, UI-owned rich text, other dashboards, or Home shortcuts.
"""
import copy
import json
import os
import sys

from native_dashboard_cli import BASE, BLOCKS as PROJECT_BLOCKS, cli, collect
from native_payment_dashboard_cli import PAYMENT_BLOCKS


DASHBOARD_ID = "blkagqTkkxI8dd8c"
TITLE = "Novogene 통합 운영 대시보드"

# UI widget identifiers are not API block_id values. Resolve the unique reviewed
# names/types from this exact dashboard, then retain those API IDs for the whole
# run. This owner cannot create a replacement when a block is renamed/missing.
SOURCE_TABLE_IDS = {
    "Project Progress Board": "tblTZe5tkRUeOHM8",
    "Weekly Quote Review": "tbl4mcccUgVHpUvO",
    "Monthly Tax Invoice": "tblXLFQWiEK9REZL",
}

SELECTIONS = (
    ("project_phase", "진행 중 AMEA 프로젝트 · 공정별", "project",
     "프로젝트 공정별 현황", "bar"),
    ("project_sif", "SIF 상태", "project",
     "SIF 상태", "pie"),
    ("payment_state", "결제 대기 상태 분포", "payment",
     "결제 대기 상태 분포", "pie"),
    ("payment_balance", "결제 대기 프로젝트 미수금 (M KRW)", "payment",
     "결제 대기 프로젝트 미수금 (M KRW)", "bar"),
    ("weekly_quote", "KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)", "project",
     "KOREA · Weekly Quote · 완료 4주 + 이번 주 (Count + 계산 K USD)", "combo"),
    ("monthly_revenue", "월별 Revenue · VAT 제외 · M KRW (K USD)", "project",
     "월별 Revenue · VAT 제외 · M KRW (K USD)", "line"),
)
# UI-owned reference wording only. A UI rich-text first line is not a verified
# API block name, so this owner never resolves, GETs, or patches the note.
NOTE = (
    "프로젝트는 진행 중 AMEA 건수입니다. 결제는 내 담당·원천 확인분이며 빈 잔액은 미확인입니다.\n"
    "견적은 Active·승인·제외 해제 건의 추정치입니다. 월별 Tax Invoice는 VAT 제외·수신월 기준이며 "
    "입금 완료나 회계상 매출 인식이 아닙니다.\n"
    "Revenue의 K USD는 1 USD=1,500 KRW 표시 환산입니다. 화면 갱신과 원본 최신성은 별개이며 "
    "상세 근거는 세부 화면에서 확인하세요."
)


def build_specs():
    """Copy verified specs without mutating either existing dashboard owner."""
    sources = {"project": PROJECT_BLOCKS, "payment": PAYMENT_BLOCKS}
    specs = []
    for key, name, source, source_name, kind in SELECTIONS:
        matches = [item for item in sources[source] if item[0] == source_name]
        if len(matches) != 1 or matches[0][1] != kind:
            raise RuntimeError("OVERVIEW_CANONICAL_SPEC_CHANGED")
        config = copy.deepcopy(matches[0][2])
        if key == "payment_balance":
            # The overview summarizes by payment state. Keep project-level
            # balances in the existing Payment dashboard's unchanged builder.
            config["group_by"] = [{"field_name": "Payment State", "mode": "integrated",
                                   "sort": {"type": "value", "order": "desc"}}]
        # No filter on the canonical monthly series means the whole canonical
        # table. An explicit empty filter also detects a UI-added hidden scope.
        config.setdefault("filter", {"conjunction": "and", "conditions": []})
        specs.append({"key": key, "name": name, "type": kind,
                      "data_config": config})
    return specs


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def comparable(key, value):
    """Normalize only documented defaults and commutative filter ordering."""
    if key == "filter":
        if value is None or value == {}:
            value = {"conjunction": "and", "conditions": []}
        if isinstance(value, dict) and isinstance(value.get("conditions"), list):
            value = copy.deepcopy(value)
            value["conditions"] = sorted(value["conditions"], key=encoded)
    return encoded(value)


def config_patch(current, expected):
    """Patch changed top-level keys; preserve presentation-only properties.

    The official CLI replaces a supplied filter/series/group_by in full and
    keeps omitted top-level keys. count_all and series are mutually exclusive.
    """
    if not isinstance(current, dict):
        raise RuntimeError("OVERVIEW_BLOCK_CONFIG_UNREADABLE")
    # The docs explicitly describe aggregation-family switching for ranking.
    # Do not assume the same removal semantics for these bar/pie/combo charts.
    if ((expected.get("count_all") is True and current.get("series"))
            or ("series" in expected and current.get("count_all") is True)):
        raise RuntimeError("OVERVIEW_AGGREGATION_FAMILY_CHANGED")
    return {key: copy.deepcopy(value) for key, value in expected.items()
            if comparable(key, current.get(key)) != comparable(key, value)}


def entity_id(row, prefix, keys):
    values = {row[key] for key in keys
              if isinstance(row.get(key), str) and row[key].startswith(prefix)}
    if len(values) > 1:
        raise RuntimeError("OVERVIEW_CONFLICTING_ENTITY_IDS")
    return next(iter(values)) if values else None


def block_id(row):
    # Returned API IDs are opaque. UI-owned components can have an unknown
    # type/name/ID prefix and must still remain in the preserved inventory.
    values = [row[key] for key in ("block_id", "id") if key in row]
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise RuntimeError("OVERVIEW_BLOCK_ID_UNREADABLE")
    if len(set(values)) != 1:
        raise RuntimeError("OVERVIEW_CONFLICTING_ENTITY_IDS")
    return values[0]


def indexed_rows(response, prefix, keys):
    result = {}
    for row in collect(response):
        ident = entity_id(row, prefix, keys)
        if ident is None or not isinstance(row.get("name"), str):
            continue
        if ident in result:
            raise RuntimeError("OVERVIEW_DUPLICATE_ENTITY_ID")
        result[ident] = row
    return result


def complete_page(response):
    pages = [row for row in collect(response) if "has_more" in row]
    if len(pages) > 1:
        raise RuntimeError("OVERVIEW_AMBIGUOUS_PAGINATION")
    if not pages:
        return None
    page = pages[0]
    if not isinstance(page["has_more"], bool):
        raise RuntimeError("OVERVIEW_INVALID_PAGINATION")
    if not page["has_more"]:
        return None
    token = page.get("page_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("OVERVIEW_MISSING_PAGE_TOKEN")
    return token


def read_dashboard(runner):
    response = runner("+dashboard-get", "--base-token", BASE,
                      "--dashboard-id", DASHBOARD_ID)
    found = [row for row in collect(response)
             if entity_id(row, "blk", ("dashboard_id", "id")) == DASHBOARD_ID
             and row.get("name") == TITLE]
    if len(found) != 1:
        raise RuntimeError("OVERVIEW_DASHBOARD_ID_OR_TITLE_MISMATCH")


def read_blocks(runner):
    rows, tokens, token = {}, set(), None
    while True:
        args = ["+dashboard-block-list", "--base-token", BASE,
                "--dashboard-id", DASHBOARD_ID, "--page-size", "100"]
        if token:
            args += ["--page-token", token]
        page = runner(*args)
        # Official block-list returns items + has_more. Read only those direct
        # items, so an arbitrary ID inside an unknown component's body cannot
        # be mistaken for a second dashboard block.
        envelopes = [node for node in collect(page)
                     if isinstance(node.get("items"), list) and "has_more" in node]
        if len(envelopes) != 1:
            raise RuntimeError("OVERVIEW_BLOCK_LIST_UNREADABLE")
        envelope = envelopes[0]
        current = {}
        for row in envelope["items"]:
            if not isinstance(row, dict):
                raise RuntimeError("OVERVIEW_BLOCK_LIST_UNREADABLE")
            ident = block_id(row)
            if ident in current:
                raise RuntimeError("OVERVIEW_DUPLICATE_BLOCK_ID")
            current[ident] = row
        if set(current) & set(rows):
            raise RuntimeError("OVERVIEW_DUPLICATE_BLOCK_ID")
        rows.update(current)
        token = complete_page({key: envelope[key] for key in ("has_more", "page_token")
                               if key in envelope})
        if token is None:
            return rows
        if token in tokens:
            raise RuntimeError("OVERVIEW_REPEATED_PAGE_TOKEN")
        tokens.add(token)


def read_block(runner, ident):
    response = runner("+dashboard-block-get", "--base-token", BASE,
                      "--dashboard-id", DASHBOARD_ID, "--block-id", ident)
    blocks = [node["block"] for node in collect(response)
              if isinstance(node.get("block"), dict)]
    if len(blocks) != 1 or block_id(blocks[0]) != ident:
        raise RuntimeError("OVERVIEW_BLOCK_ID_MISMATCH")
    row = blocks[0]
    if not isinstance(row.get("data_config"), dict):
        raise RuntimeError("OVERVIEW_BLOCK_CONFIG_UNREADABLE")
    return row


def resolve_inventory(rows, specs):
    managed_ids = {}
    for spec in specs:
        matches = [(ident, row) for ident, row in rows.items()
                   if row.get("name") == spec["name"]]
        if not matches:
            raise RuntimeError("OVERVIEW_MANAGED_BLOCK_MISSING")
        if len(matches) != 1:
            raise RuntimeError("OVERVIEW_DUPLICATE_NAMED_BLOCK")
        ident, row = matches[0]
        if row.get("type") != spec["type"]:
            raise RuntimeError("OVERVIEW_BLOCK_TYPE_MISMATCH")
        managed_ids[spec["key"]] = ident
    return managed_ids


def validate_block_identity(row, spec):
    if row.get("name") != spec["name"] or row.get("type") != spec["type"]:
        raise RuntimeError("OVERVIEW_BLOCK_NAME_OR_TYPE_CHANGED")
    if row["data_config"].get("table_name") != spec["data_config"]["table_name"]:
        raise RuntimeError("OVERVIEW_BLOCK_SOURCE_CHANGED")


def required_fields(specs):
    required = {}
    for spec in specs:
        config = spec["data_config"]
        fields = required.setdefault(config["table_name"], {})
        for item in config.get("series", []):
            fields[item["field_name"]] = "number"
        for item in config.get("group_by", []):
            fields.setdefault(item["field_name"], "text")
        for item in config.get("filter", {}).get("conditions", []):
            expected = "checkbox" if isinstance(item.get("value"), bool) else "text"
            fields.setdefault(item["field_name"], expected)
    return required


def source_catalog(response, prefix, id_keys, error):
    rows = indexed_rows(response, prefix, id_keys)
    # +table-list/+field-list v1.0.99 expose offset/limit pagination as a total,
    # not has_more. Never accept a truncated page as a complete name catalog.
    totals = [node["total"] for node in collect(response) if "total" in node]
    if (complete_page(response) is not None or len(totals) != 1
            or isinstance(totals[0], bool) or not isinstance(totals[0], int)
            or totals[0] != len(rows)):
        raise RuntimeError(error)
    return rows


def verify_source_schema(runner, specs):
    # Read metadata only: no record scans and no implied source freshness.
    tables = runner("+table-list", "--base-token", BASE)
    index = source_catalog(tables, "tbl", ("table_id", "id"),
                           "OVERVIEW_SOURCE_CATALOG_INCOMPLETE")
    for name, required in required_fields(specs).items():
        matches = [ident for ident, row in index.items() if row["name"] == name]
        if len(matches) != 1:
            raise RuntimeError("OVERVIEW_SOURCE_TABLE_MISSING_OR_DUPLICATE")
        if SOURCE_TABLE_IDS.get(name) != matches[0]:
            raise RuntimeError("OVERVIEW_SOURCE_TABLE_ID_MISMATCH")
        response = runner("+field-list", "--base-token", BASE,
                          "--table-id", matches[0])
        fields = source_catalog(response, "fld", ("field_id", "id"),
                                "OVERVIEW_SOURCE_SCHEMA_INCOMPLETE")
        for field, expected_type in required.items():
            matches = [row for row in fields.values() if row["name"] == field]
            if len(matches) != 1:
                raise RuntimeError("OVERVIEW_SOURCE_FIELD_MISSING_OR_DUPLICATE")
            if expected_type and matches[0].get("type") != expected_type:
                raise RuntimeError("OVERVIEW_SOURCE_FIELD_TYPE_MISMATCH")


def reconcile(mode, runner=cli):
    if mode not in {"plan", "verify", "apply"}:
        raise RuntimeError("OVERVIEW_BAD_MODE")
    specs = build_specs()
    read_dashboard(runner)
    initial = read_blocks(runner)
    managed_ids = resolve_inventory(initial, specs)
    verify_source_schema(runner, specs)
    changes = []
    # Read and validate every owned block before the first mutation.
    for spec in specs:
        ident = managed_ids[spec["key"]]
        row = read_block(runner, ident)
        validate_block_identity(row, spec)
        patch = config_patch(row["data_config"], spec["data_config"])
        if patch:
            changes.append((spec, ident, patch))
    if mode == "verify" and changes:
        raise RuntimeError("OVERVIEW_CONFIG_DRIFT_" + str(len(changes)))
    if mode == "apply":
        for spec, ident, patch in changes:
            runner("+dashboard-block-update", "--base-token", BASE,
                   "--dashboard-id", DASHBOARD_ID, "--block-id", ident,
                   "--data-config", encoded(patch))
            updated = read_block(runner, ident)
            validate_block_identity(updated, spec)
            if config_patch(updated["data_config"], spec["data_config"]):
                raise RuntimeError("OVERVIEW_CONFIG_READBACK_MISMATCH")
        final = read_blocks(runner)
        if resolve_inventory(final, specs) != managed_ids:
            raise RuntimeError("OVERVIEW_BLOCK_ID_CHANGED_DURING_APPLY")
        if not set(initial).issubset(final):
            raise RuntimeError("OVERVIEW_EXISTING_BLOCK_DISAPPEARED")
        read_dashboard(runner)
    inventory = [{"name": spec["name"], "block_id": managed_ids[spec["key"]],
                  "type": spec["type"], "source_table_id": SOURCE_TABLE_IDS.get(
                      spec["data_config"].get("table_name"))} for spec in specs]
    return {"mode": mode, "blocks": len(specs), "drift": len(changes),
            "writes": len(changes) if mode == "apply" else 0, "inventory": inventory}


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != BASE:
        raise RuntimeError("OVERVIEW_REFUSE_OTHER_BASE")
    result = reconcile(os.environ.get("FEISHU_OVERVIEW_MODE", "plan"))
    inventory = result.pop("inventory")
    print("FEISHU_NATIVE_OVERVIEW_PASS " + " ".join(
        str(key) + "=" + str(value) for key, value in result.items()) +
        " customer_rows_written=0 dashboard=" + DASHBOARD_ID)
    # No row data, names of customers, filter values, or credentials in logs.
    print("FEISHU_NATIVE_OVERVIEW_INVENTORY=" + encoded(inventory))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("FEISHU_NATIVE_OVERVIEW_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
