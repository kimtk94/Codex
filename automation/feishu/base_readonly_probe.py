#!/usr/bin/env python3
"""Read-only Feishu Base connectivity and metadata probe. Never prints tokens or record fields."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = "https://open.feishu.cn"
def request(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(ROOT + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {path.split('?')[0]}") from None

def require(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub Actions secret: {name}")
    return value

def main():
    app_id = require("FEISHU_APP_ID")
    app_secret = require("FEISHU_APP_SECRET")
    base = require("FEISHU_BASE_APP_TOKEN")
    auth = request("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                   body={"app_id": app_id, "app_secret": app_secret})
    if auth.get("code") != 0 or not auth.get("tenant_access_token"):
        raise RuntimeError("Feishu authentication failed (check app credentials and approval)")
    token = auth["tenant_access_token"]
    print("AUTH: PASS")
    prefix = "/open-apis/bitable/v1/apps/" + urllib.parse.quote(base, safe="")
    cursor = ""
    tables = []
    while True:
        qs = "?page_size=100" + ("&page_token=" + urllib.parse.quote(cursor, safe="") if cursor else "")
        response = request("GET", prefix + "/tables" + qs, token=token)
        if response.get("code") != 0:
            raise RuntimeError("Base tables API rejected request: code=" + str(response.get("code")))
        d = response.get("data") or {}
        tables.extend({"table_id": item.get("table_id"), "name": item.get("name")}
                      for item in d.get("items") or [])
        if not d.get("has_more"):
            break
        cursor = d.get("page_token")
        if not cursor:
            raise RuntimeError("Missing pagination cursor")
    print("BASE_ACCESS: PASS")
    print("TABLE_COUNT:", len(tables))
    for table in tables:
        print("TABLE:", table["table_id"], json.dumps(table["name"], ensure_ascii=False))
    table_name = os.environ.get("FEISHU_TABLE_NAME", "표").strip()
    view_name = os.environ.get("FEISHU_VIEW_NAME", "Taehoon").strip()
    matching = [t for t in tables if t["name"] == table_name]
    if len(matching) != 1:
        raise RuntimeError(f"Expected exactly one table named {table_name!r}; found {len(matching)}")
    table_id = matching[0]["table_id"]
    print("TARGET_TABLE:", table_name, table_id)
    path = prefix + "/tables/" + urllib.parse.quote(table_id, safe="")
    views = []
    cursor = ""
    while True:
        qs = "?page_size=100" + ("&page_token=" + urllib.parse.quote(cursor, safe="") if cursor else "")
        response = request("GET", path + "/views" + qs, token=token)
        if response.get("code") != 0:
            raise RuntimeError("View list failed: code=" + str(response.get("code")))
        d = response.get("data") or {}
        views.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        cursor = d.get("page_token")
        if not cursor:
            raise RuntimeError("Missing views pagination cursor")
    selected = [v for v in views if v.get("view_name") == view_name]
    if len(selected) != 1:
        raise RuntimeError(f"Expected exactly one view named {view_name!r}; found {len(selected)}")
    view_id = selected[0]["view_id"]
    print("TARGET_VIEW:", view_name, view_id)
    qs = urllib.parse.urlencode({"page_size": 1, "view_id": view_id})
    response = request("GET", path + "/records?" + qs, token=token)
    if response.get("code") != 0:
        raise RuntimeError("View record read failed: code=" + str(response.get("code")))
    d = response.get("data") or {}
    print("RECORD_READ: PASS (fields and values suppressed)")
    print("SAMPLE_RECORD_COUNT:", len(d.get("items") or []))

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, urllib.error.URLError, ValueError) as exc:
        print("CHECK_FAILED:", str(exc), file=sys.stderr)
        sys.exit(1)
