#!/usr/bin/env python3
"""Read-only Feishu Wiki/Base connectivity probe. Never logs record contents."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HOST = "https://open.feishu.cn/open-apis"
WIKI_TOKEN = "BUHTwWF5GidC3ekjWmEcMYFhnZc"
TABLE_ID = "wbpD7kQYkQ"

def request(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP " + str(exc.code) + " on " + path.split("?")[0]) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Network failure (" + type(exc).__name__ + ")") from None

def check(payload, stage):
    if payload.get("code") != 0:
        # Feishu may include sensitive metadata in msg: show only numeric error code.
        raise RuntimeError(stage + " failed: Feishu code=" + str(payload.get("code")))
    return payload.get("data") or {}

def main():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("CONFIG_MISSING: FEISHU_APP_ID or FEISHU_APP_SECRET")
        return 2
    try:
        auth = request("POST", "/auth/v3/tenant_access_token/internal", body={"app_id": app_id, "app_secret": app_secret})
        check(auth, "authentication")
        token = auth.get("tenant_access_token")
        if not token:
            raise RuntimeError("Authentication response lacks tenant_access_token")
        print("AUTH_OK")
        path = "/wiki/v2/spaces/get_node?" + urllib.parse.urlencode({"token": WIKI_TOKEN})
        wiki = check(request("GET", path, token=token), "wiki resolution")
        node = wiki.get("node") or {}
        obj_type, obj_token = node.get("obj_type"), node.get("obj_token")
        if obj_type != "bitable" or not obj_token:
            raise RuntimeError("Wiki node not resolved to Base (object_type=" + str(obj_type) + ")")
        print("WIKI_BASE_RESOLVED")
        base = urllib.parse.quote(obj_token, safe="")
        table = urllib.parse.quote(TABLE_ID, safe="")
        fields = check(request("GET", "/bitable/v1/apps/" + base + "/tables/" + table + "/fields?page_size=1", token=token), "fields")
        print("FIELDS_READ_OK (pagination_flag=" + str(bool(fields.get("has_more"))) + ")")
        records = check(request("GET", "/bitable/v1/apps/" + base + "/tables/" + table + "/records?page_size=1", token=token), "records")
        print("RECORDS_READ_OK (pagination_flag=" + str(bool(records.get("has_more"))) + ")")
        print("PROBE_PASS: no rows or cells printed, saved, or uploaded")
        return 0
    except (RuntimeError, ValueError, KeyError) as exc:
        print("PROBE_FAILED: " + str(exc))
        return 1

if __name__ == "__main__":
    sys.exit(main())
