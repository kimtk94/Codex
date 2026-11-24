#!/usr/bin/env python3
"""Provision a project-only native dashboard, without duplicating records.

Plan/verify are read-only. Apply creates missing components only. An existing
page requires its reviewed ID. Never modify existing blocks, views or records.
"""
import argparse
import os
import sys

from native_dashboard_cli import BASE, TABLE, cli, collect, validate_dashboard_layout
from native_overview_dashboard import (
    SOURCE_TABLE_IDS, block_id, config_patch, encoded, verify_source_schema,
)

TABLE_ID = SOURCE_TABLE_IDS[TABLE]

TITLE = "Novogene 프로젝트 관리 센터"
ACTIVE, PAYMENT, ARCHIVE = "PRODUCTION_ACTIVE", "PAYMENT_FOLLOWUP", "PAID_ARCHIVED"


def cond(field, value=None, operator="is"):
    item = {"field_name": field, "operator": operator}
    if operator not in {"isEmpty", "isNotEmpty"}:
        item["value"] = value
    return item


def scope(lane, *conditions):
    base = [cond("Workflow Lane", lane)]
    if lane in {PAYMENT, ARCHIVE}:
        base.append(cond("Payment Owner Scope", "MY_VERIFIED"))
    return {"conjunction": "and", "conditions": [*base, *conditions]}


def spec(name, kind, config, x, y, w, h):
    return {"name": name, "type": kind, "data_config": config,
            "position": dict(x=x, y=y, w=w, h=h)}


def count(name, filt, x, y):
    return spec(name, "statistics", {
        "table_name": TABLE, "count_all": True, "filter": filt,
        "number_format": {"formatName": "digital", "precision": 0},
    }, x, y, 3, 4)


def distribution(name, field, filt, x, y, kind="bar"):
    return spec(name, kind, {
        "table_name": TABLE, "count_all": True, "filter": filt,
        "group_by": [{"field_name": field, "mode": "integrated",
                      "sort": {"type": "group", "order": "asc"}}],
    }, x, y, 6, 7)


def navigation_note():
    # Official CLI v1.0.99 text blocks do not support Markdown links.
    # Native clickable shortcuts must be verified separately in the UI.
    return (
        "# Project Management Center\n"
        "**업무:** Project Progress Board의 01 오늘 확인 · 00 관리 작업대 · "
        "02 관리 칸반 · 03 확인 일정\n"
        "**위험:** 04 위험 검토 · PM Risk / PM Issue / PM Recommended Action\n"
        "**상세:** 진행 중 프로젝트 · 완료 · 결제 관리 · 결제 완료 · 보관"
    )


def build_specs():
    items = [
        spec("업무 안내", "text", {"text": navigation_note()}, 0, 0, 12, 5),
        count("보드상 진행 중", scope(ACTIVE), 0, 5),
        count("자동 위험 HIGH", scope(ACTIVE, cond("PM Risk", "HIGH")), 3, 5),
        count("원본 확인 UNKNOWN", scope(ACTIVE, cond("PM Risk", "UNKNOWN")), 6, 5),
        count("내 담당 결제 확인", scope(PAYMENT), 9, 5),
        distribution("프로젝트 공정 분포", "Progress Phase", scope(ACTIVE), 0, 9),
        distribution("자동 위험 신호 분포", "PM Risk", scope(ACTIVE), 6, 9, "pie"),
        distribution("자동 이슈 유형", "PM Issue", scope(ACTIVE), 0, 16),
        distribution("진행 중 SIF 상태", "SIF State", scope(ACTIVE), 6, 16, "pie"),
        distribution("내 담당 결제 상태", "Payment State", scope(PAYMENT), 0, 23, "pie"),
        spec("내 담당 미수금 (M KRW)", "bar", {
            "table_name": TABLE, "filter": scope(PAYMENT),
            "series": [{"field_name": "Outstanding Balance M KRW", "rollup": "SUM"}],
            "group_by": [{"field_name": "Payment State", "mode": "integrated",
                          "sort": {"type": "value", "order": "desc"}}],
        }, 6, 23, 6, 7),
        count("위험 신호 미계산", scope(ACTIVE, cond("PM Risk", operator="isEmpty")), 0, 30),
        count("내 담당 결제 위험 HIGH", scope(PAYMENT, cond("PM Risk", "HIGH")), 3, 30),
        count("내 담당 입금 검증 보관", scope(ARCHIVE), 6, 30),
        spec("해석 및 범위", "text", {"text": (
            "보드상 상태 및 마지막 분류 기준입니다. 이전 보존 행도 남을 수 있으므로 "
            "원본 최신성은 별도 점검하세요. HIGH는 확인 이슈의 조치 우선순위이며 "
            "납기 초과 판정이 아닙니다. MONITOR도 정상 납기를 보장하지 않습니다. "
            "UNKNOWN·미계산은 검토 대상입니다. 결제는 원천 내 담당 일치 건만 표시하며 "
            "미확인 잔액은 0원 확정이 아닙니다. 오늘 확인과 일정은 사람이 입력한 확인일 기준입니다."
        )}, 0, 34, 12, 4),
    ]
    validate_dashboard_layout(
        [(r["name"], r["type"], r["data_config"]) for r in items],
        {r["name"]: r["position"] for r in items},
    )
    return items


def dashboard_identity(row):
    # API identifiers are opaque; do not reject unrelated ID formats.
    values = [row[key] for key in ("dashboard_id", "id") if key in row]
    if not values or any(not isinstance(v, str) or not v for v in values):
        raise RuntimeError("PROJECT_CENTER_DASHBOARD_ID_UNREADABLE")
    if len(set(values)) != 1:
        raise RuntimeError("PROJECT_CENTER_DASHBOARD_ID_CONFLICT")
    return values[0]


def response_entity(response, key):
    rows = [r[key] for r in collect(response) if isinstance(r.get(key), dict)]
    if len(rows) != 1:
        raise RuntimeError("PROJECT_CENTER_ENTITY_RESPONSE_UNREADABLE")
    return rows[0]


def inventory(runner, operation, dashboard_id=None):
    """Require a complete items/has_more catalog."""
    result, seen, token = {}, set(), None
    while True:
        args = [operation, "--base-token", BASE, "--page-size", "100"]
        if dashboard_id:
            args += ["--dashboard-id", dashboard_id]
        if token:
            args += ["--page-token", token]
        response = runner(*args)
        envelopes = [r for r in collect(response)
                     if isinstance(r.get("items"), list) and "has_more" in r]
        if len(envelopes) != 1:
            raise RuntimeError("PROJECT_CENTER_LIST_UNREADABLE")
        listing = envelopes[0]
        for row in listing["items"]:
            if not isinstance(row, dict):
                raise RuntimeError("PROJECT_CENTER_LIST_UNREADABLE")
            ident = block_id(row) if dashboard_id else dashboard_identity(row)
            if not ident or ident in result:
                raise RuntimeError("PROJECT_CENTER_INVALID_OR_DUPLICATE_ID")
            if not dashboard_id and not isinstance(row.get("name"), str):
                raise RuntimeError("PROJECT_CENTER_DASHBOARD_NAME_UNREADABLE")
            result[ident] = row
        if listing["has_more"] is False:
            return result
        token = listing.get("page_token")
        if listing["has_more"] is not True or not isinstance(token, str) or not token or token in seen:
            raise RuntimeError("PROJECT_CENTER_INCOMPLETE_LIST")
        seen.add(token)


def locate(runner):
    rows = inventory(runner, "+dashboard-list")
    found = [ident for ident, row in rows.items() if row.get("name") == TITLE]
    if len(found) > 1:
        raise RuntimeError("PROJECT_CENTER_DUPLICATE_TITLE")
    return found[0] if found else None


def inspect(runner, ident, specs):
    data = runner("+dashboard-get", "--base-token", BASE, "--dashboard-id", ident)
    found = response_entity(data, "dashboard")
    if dashboard_identity(found) != ident or found.get("name") != TITLE:
        raise RuntimeError("PROJECT_CENTER_PAGE_ID_MISMATCH")
    rows = inventory(runner, "+dashboard-block-list", ident)
    managed, missing, drift = {}, [], []
    for target in specs:
        name = target["name"]
        matches = [i for i, r in rows.items() if r.get("name") == name]
        if len(matches) > 1:
            raise RuntimeError("PROJECT_CENTER_DUPLICATE_BLOCK")
        if not matches:
            missing.append(target)
            continue
        bid = matches[0]
        response = runner("+dashboard-block-get", "--base-token", BASE,
                          "--dashboard-id", ident, "--block-id", bid)
        blocks = [r["block"] for r in collect(response) if isinstance(r.get("block"), dict)]
        if len(blocks) != 1 or block_id(blocks[0]) != bid:
            raise RuntimeError("PROJECT_CENTER_BLOCK_ID_MISMATCH")
        block = blocks[0]
        if block.get("name") != name or block.get("type") != target["type"]:
            raise RuntimeError("PROJECT_CENTER_BLOCK_IDENTITY_CHANGED")
        current = block.get("data_config")
        if not isinstance(current, dict):
            raise RuntimeError("PROJECT_CENTER_CONFIG_UNREADABLE")
        if target["type"] != "text" and current.get("table_name") != TABLE:
            raise RuntimeError("PROJECT_CENTER_WRONG_SOURCE")
        if config_patch(current, target["data_config"]):
            drift.append(name)
        managed[name] = bid
    return rows, managed, missing, drift


def reconcile(mode="plan", expected_id="", runner=cli):
    if mode not in {"plan", "verify", "apply"}:
        raise RuntimeError("PROJECT_CENTER_BAD_MODE")
    specs = build_specs()
    verify_source_schema(runner, [s for s in specs if s["type"] != "text"])
    ident = locate(runner)
    if expected_id and ident != expected_id:
        raise RuntimeError("PROJECT_CENTER_EXPECTED_ID_MISMATCH")
    created = False
    if not ident:
        if mode == "verify":
            raise RuntimeError("PROJECT_CENTER_PAGE_MISSING")
        if mode == "plan":
            return {"dashboard": None, "missing": len(specs), "drift": 0, "writes": 0}
        response = runner("+dashboard-create", "--base-token", BASE, "--name", TITLE)
        new_page = response_entity(response, "dashboard")
        ident = dashboard_identity(new_page)
        if new_page.get("name") != TITLE or locate(runner) != ident:
            raise RuntimeError("PROJECT_CENTER_CREATE_READBACK_FAILED")
        created = True
    rows, managed, missing, drift = inspect(runner, ident, specs)
    if mode == "plan":
        return {"dashboard": ident, "missing": len(missing), "drift": len(drift), "writes": 0}
    if mode == "verify":
        if missing or drift:
            raise RuntimeError("PROJECT_CENTER_CONFIG_REVIEW_REQUIRED")
        return {"dashboard": ident, "missing": 0, "drift": 0, "writes": 0}
    if not created and expected_id != ident:
        raise RuntimeError("PROJECT_CENTER_REVIEW_EXISTING_ID_FIRST")
    if drift:
        raise RuntimeError("PROJECT_CENTER_CONFIG_REVIEW_REQUIRED")
    # Sequential create. Existing pages keep their UI-owned positions.
    created_ids = {}
    for target in missing:
        current = inventory(runner, "+dashboard-block-list", ident)
        # Confirm prior writes before creating another block. An invisible
        # write may be partially committed; stop rather than accumulating more.
        if not set(created_ids.values()).issubset(current) or not set(rows).issubset(current):
            raise RuntimeError("PROJECT_CENTER_READBACK_FAILED")
        if any(current[bid].get("name") != name for name, bid in created_ids.items()):
            raise RuntimeError("PROJECT_CENTER_READBACK_FAILED")
        if any(r.get("name") == target["name"] for r in current.values()):
            raise RuntimeError("PROJECT_CENTER_CONCURRENT_CREATE_REVIEW")
        args = ["+dashboard-block-create", "--base-token", BASE, "--dashboard-id", ident,
                "--name", target["name"], "--type", target["type"],
                "--data-config", encoded(target["data_config"])]
        if created:
            args += ["--position", encoded(target["position"])]
        response = runner(*args)
        block = response_entity(response, "block")
        bid = block_id(block)
        if bid in current or bid in created_ids.values():
            raise RuntimeError("PROJECT_CENTER_CREATE_ID_COLLISION")
        if block.get("name") != target["name"] or block.get("type") != target["type"]:
            raise RuntimeError("PROJECT_CENTER_CREATE_BLOCK_MISMATCH")
        created_ids[target["name"]] = bid
    final, final_managed, still_missing, final_drift = inspect(runner, ident, specs)
    if (still_missing or final_drift or not set(rows).issubset(final)
            or any(final_managed.get(n) != i for n, i in {**managed, **created_ids}.items())):
        raise RuntimeError("PROJECT_CENTER_READBACK_FAILED")
    if locate(runner) != ident:
        raise RuntimeError("PROJECT_CENTER_PAGE_CHANGED")
    # Report server auto-layout differences rather than move existing blocks.
    layout_review = created and any(
        final[final_managed[s["name"]]].get("position") != s["position"] for s in specs)
    return {"dashboard": ident, "missing": 0, "drift": 0,
            "writes": int(created) + len(missing), "layout_review": layout_review}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("plan", "verify", "apply"), default="plan")
    parser.add_argument("--expected-dashboard-id", default="")
    args = parser.parse_args()
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != BASE:
        raise RuntimeError("PROJECT_CENTER_REFUSE_OTHER_BASE")
    output = reconcile(args.mode, args.expected_dashboard_id)
    print("PROJECT_CENTER_PASS " + encoded(output))
    # Do not fabricate a browser URL for an unverified API ID format.
    if output.get("dashboard") and output["dashboard"].startswith("blk"):
        print("PROJECT_CENTER_URL=https://ocnz4cb25scn.feishu.cn/base/" + BASE
              + "?table=" + output["dashboard"])
    print("PROJECT_CENTER_RECORD_WRITES=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PROJECT_CENTER_FAILED=" + (str(exc) if isinstance(exc, RuntimeError)
              else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
