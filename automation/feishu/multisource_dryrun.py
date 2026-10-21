#!/usr/bin/env python3
"""P0 multi-source Feishu sync preflight: metadata only, no writes or user data logs."""
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = "https://open.feishu.cn"
TABLE = "tblCOdjgmWmKyhnb"
VIEW = "vewZo2Z3zA"

def get_json(path, token=None, data=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(ROOT + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as res:
        response = json.load(res)
    if response.get("code") != 0:
        raise RuntimeError("Feishu rejected API request: code=" + str(response.get("code")))
    return response.get("data") or response

def pages(prefix, token):
    cursor = ""
    seen = set()
    while True:
        params = {"page_size": 100}
        if cursor:
            params["page_token"] = cursor
        d = get_json(prefix + "?" + urllib.parse.urlencode(params), token)
        for item in d.get("items") or []:
            yield item
        if not d.get("has_more"):
            return
        next_cursor = d.get("page_token")
        if not next_cursor or next_cursor in seen:
            raise RuntimeError("Pagination cursor invalid")
        seen.add(next_cursor)
        cursor = next_cursor

def main():
    for key in ("FEISHU_APP_ID","FEISHU_APP_SECRET","FEISHU_BASE_APP_TOKEN"):
        if not os.environ.get(key):
            raise RuntimeError("Missing secret: " + key)
    d = get_json("/open-apis/auth/v3/tenant_access_token/internal",
                 data={"app_id": os.environ["FEISHU_APP_ID"], "app_secret": os.environ["FEISHU_APP_SECRET"]})
    token = d["tenant_access_token"]
    prefix = "/open-apis/bitable/v1/apps/" + urllib.parse.quote(os.environ["FEISHU_BASE_APP_TOKEN"], safe="") + "/tables/" + TABLE
    fields = list(pages(prefix + "/fields", token))
    if not fields:
        raise RuntimeError("Empty field metadata")
    views = list(pages(prefix + "/views", token))
    if not any(v.get("view_id") == VIEW and v.get("view_name") == "Taehoon" for v in views):
        raise RuntimeError("Target view mismatch")
    # Feishu field names are considered metadata; do not log them by default.
    print("AUTH: PASS")
    print("TARGET_VIEW: PASS")
    print("SCHEMA_FIELD_COUNT:", len(fields))
    print("FIELD_TYPE_COUNTS:", json.dumps({str(t):sum(f.get("type")==t for f in fields) for t in sorted({f.get("type") for f in fields})}, sort_keys=True))
    # Fail-closed write gating; actual update/create code is intentionally not invoked.
    print("WRITE_ACCESS: NOT_TESTED (no safe permission-only endpoint verified)")
    print("DRY_RUN: PASS (no mutations)")
    print("SOURCE_SFDC: MAPPING_REQUIRED (Salesforce Lead Tracker / Enquiry Queue / Engagements)")
    print("SOURCE_MAIL: MAPPING_REQUIRED (do not infer sent-mail state)")
    print("PROPOSED_UPDATES: 0")
    print("PROPOSED_CREATES: 0")
    print("WRITE_OPERATIONS: 0")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not echo remote messages or payloads; they may contain sensitive data.
        print("PREFLIGHT_FAILED:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
