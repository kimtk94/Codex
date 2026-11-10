#!/usr/bin/env python3
"""Idempotently repair Novogene Sales Home links in the *specific* Feishu Base.

Only three whitelisted Menu Key records may be changed.  Original project
records, finance data, lifecycle filters and dashboard data are never touched.
Run in audit mode by default; --apply explicitly enables writes.
"""
import argparse
import os
import urllib.parse

from base_readonly_probe import request, require

BASE = "IpMkbUD0vaFqtYs93a3csXtdn1b"
HOST = "ocnz4cb25scn.feishu.cn"
HOME_TABLE = "tblmnRSJI05zYVjw"
HOME_VIEW = "vewg73eb8z"
PROJECT_BOARD = "tblTZe5tkRUeOHM8"
EXPECTED_VIEWS = {
    "진행 중 프로젝트": "vew9v3YnBX",
    "완료 · 결제 관리": "vewzKSaZ1p",
    "결제 완료 · 보관": "vewIKJf0Fj",
}
TARGETS = {
    "WEEKLY_TREND": ("blkDo2hZZajDNR87", None),
    "MONTHLY_TREND": ("blk6h2KPqrSzEAlG", None),
    "X_MY_PROJECTS": ("blkzYT2OAVQssL3Y", "07 · 프로젝트 운영 대시보드"),
}
API = "/open-apis/bitable/v1/apps/" + BASE

def url(block):
    return f"https://{HOST}/base/{BASE}?table={block}"

def require_success(response, label):
    if not isinstance(response, dict) or response.get("code") != 0:
        raise RuntimeError(label + "_API_ERROR_" + str(response.get("code") if isinstance(response, dict) else "BAD_JSON"))
    return response.get("data") or {}

def pages(path, token, extra=None):
    cursor = ""
    count = 0
    while True:
        params = {"page_size": 100}
        if extra:
            params.update(extra)
        if cursor:
            params["page_token"] = cursor
        qs = urllib.parse.urlencode(params)
        data = require_success(request("GET", path + "?" + qs, token=token), "LIST")
        for row in data.get("items") or []:
            yield row
        count += 1
        if not data.get("has_more"):
            break
        new_cursor = data.get("page_token")
        if not new_cursor or new_cursor == cursor or count > 100:
            raise RuntimeError("UNSAFE_PAGINATION")
        cursor = new_cursor

def extract_token(response):
    """Auth v3 returns tenant_access_token at the response top level."""
    if not isinstance(response, dict) or response.get("code") != 0:
        raise RuntimeError("AUTH_API_ERROR_" + str(response.get("code") if isinstance(response, dict) else "BAD_JSON"))
    token = response.get("tenant_access_token") or (response.get("data") or {}).get("tenant_access_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("FEISHU_TOKEN_UNAVAILABLE")
    return token

def link_url(value):
    if isinstance(value, dict):
        return str(value.get("link") or "")
    if isinstance(value, list) and len(value) == 1:
        return link_url(value[0])
    if value in (None, ""):
        return ""
    raise RuntimeError("UNRECOGNIZED_EXISTING_LINK")

def validate_current_link(value):
    existing = link_url(value).strip()
    if not existing:
        return
    parsed = urllib.parse.urlparse(existing)
    params = urllib.parse.parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.hostname != HOST
            or parsed.path != "/base/" + BASE or not params.get("table")):
        raise RuntimeError("EXISTING_LINK_NOT_SAME_BASE")

def plan(records):
    by_key = {}
    for row in records:
        f = row.get("fields") or {}
        key = f.get("Menu Key")
        if key not in TARGETS:
            continue
        if key in by_key:
            raise RuntimeError("DUPLICATE_MENU_KEY")
        if not row.get("record_id"):
            raise RuntimeError("MISSING_RECORD_ID")
        validate_current_link(f.get("바로가기"))
        block, label = TARGETS[key]
        desired = url(block)
        update = {}
        if link_url(f.get("바로가기")) != desired:
            update["바로가기"] = {"text": "열기", "link": desired}
        if label is not None and f.get("화면") != label:
            update["화면"] = label
        by_key[key] = {"id": row["record_id"], "fields": update}
    if set(by_key) != set(TARGETS):
        raise RuntimeError("MISSING_HOME_MENU_KEY")
    return by_key

def verify_views(token):
    base = API + "/tables/" + PROJECT_BOARD
    views = list(pages(base + "/views", token))
    mapping = {v.get("view_name"): v.get("view_id") for v in views}
    for name, identifier in EXPECTED_VIEWS.items():
        if mapping.get(name) != identifier:
            raise RuntimeError("PROJECT_LIFECYCLE_VIEW_MISMATCH")
    fields = {f.get("field_name") for f in pages(base + "/fields", token)}
    if "Quote Full Name" not in fields or "Source Key" not in fields:
        raise RuntimeError("PROJECT_ID_FIELDS_MISSING")
    print("PROJECT_VIEWS_VALIDATED=3 QUOTE_NAME_FIELD_PRESENT=1", flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and os.getenv("FEISHU_SALES_HOME_APPLY") != "1":
        raise RuntimeError("APPLY_FLAG_NOT_AUTHORIZED")
    auth = request(
        "POST", "/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id": require("FEISHU_APP_ID"), "app_secret": require("FEISHU_APP_SECRET")}
    )
    token = extract_token(auth)
    path = API + "/tables/" + HOME_TABLE
    fields = {f.get("field_name") for f in pages(path + "/fields", token)}
    if not {"Menu Key", "바로가기", "화면"}.issubset(fields):
        raise RuntimeError("HOME_FIELDS_MISSING")
    verify_views(token)
    data = list(pages(path + "/records", token, {"view_id": HOME_VIEW}))
    changes = plan(data)
    pending = sum(bool(item["fields"]) for item in changes.values())
    print(f"HOME_LINK_AUDIT keys={len(changes)} pending={pending} mode={'APPLY' if args.apply else 'DRY_RUN'}", flush=True)
    if not args.apply:
        return
    # Preflight all three rows before first write; never update any unrelated row.
    for key in TARGETS:
        item = changes[key]
        if not item["fields"]:
            print("HOME_LINK_ALREADY_CURRENT " + key, flush=True)
            continue
        record_path = path + "/records/" + urllib.parse.quote(item["id"], safe="")
        require_success(request("PUT", record_path, token=token,
                                body={"fields": item["fields"]}), "WRITE_" + key)
        latest = require_success(request("GET", record_path, token=token), "VERIFY_" + key)
        actual = (latest.get("record") or {}).get("fields") or {}
        for field, expected in item["fields"].items():
            if field == "바로가기":
                if link_url(actual.get(field)) != expected["link"]:
                    raise RuntimeError("LINK_READBACK_FAILED_" + key)
            elif actual.get(field) != expected:
                raise RuntimeError("LABEL_READBACK_FAILED_" + key)
        print("HOME_LINK_VERIFIED " + key, flush=True)
    print("HOME_LINK_SYNC_PASS updated=" + str(pending), flush=True)

if __name__ == "__main__":
    main()
