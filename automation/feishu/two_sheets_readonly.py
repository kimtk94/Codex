#!/usr/bin/env python3
"""Read-only, log-safe Feishu Sheets probe for two explicitly authorized tabs."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCES = (
    ("feishu_1", "NAK9smybJhuEvet9u93jaeSqpSg", "NIcvsT"),
    ("feishu_2", "MoZasLAK8hUlsAtIhumjVHjYpQe", "2jUIBX"),
)
HOST = "https://open.feishu.cn"


def request(path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        # Never echo the raw Feishu response, credentials, or cell contents.
        raise RuntimeError("HTTP_STATUS_" + str(exc.code)) from None
    if not isinstance(result, dict) or result.get("code") != 0:
        code = result.get("code") if isinstance(result, dict) else "INVALID_RESPONSE"
        raise RuntimeError("FEISHU_CODE_" + str(code))
    return result.get("data") or result


def run():
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    auth = request("/open-apis/auth/v3/tenant_access_token/internal",
                   body={"app_id": app_id, "app_secret": app_secret})
    token = auth.get("tenant_access_token")
    if not token:
        raise RuntimeError("TENANT_TOKEN_MISSING")
    print("AUTH: PASS")
    failures = []
    for name, spreadsheet, sheet_id in SOURCES:
        try:
            base = "/open-apis/sheets/v3/spreadsheets/" + urllib.parse.quote(spreadsheet, safe="")
            info = request(base + "/sheets/query", token)
            tabs = info.get("sheets")
            if not isinstance(tabs, list):
                raise RuntimeError("SHEETS_LIST_UNAVAILABLE")
            if sheet_id not in {s.get("sheet_id") for s in tabs if isinstance(s, dict)}:
                raise RuntimeError("TARGET_TAB_MISSING")
            # Header-only read validates actual cells permission; no content printed or persisted.
            span = urllib.parse.quote(sheet_id + "!A1:AZ1", safe="!:")
            values = request("/open-apis/sheets/v2/spreadsheets/" +
                             urllib.parse.quote(spreadsheet, safe="") +
                             "/values/" + span, token)
            value_range = values.get("valueRange")
            if not isinstance(value_range, dict):
                raise RuntimeError("VALUE_RANGE_MISSING")
            headers = (value_range.get("values") or [[]])[0]
            print(name + ": READ_PASS; HEADER_COLUMNS=" + str(len(headers)) +
                  "; TAB_COUNT=" + str(len(tabs)))
        except (RuntimeError, urllib.error.URLError, TimeoutError, KeyError, IndexError) as exc:
            reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            print(name + ": READ_FAIL; REASON=" + reason, file=sys.stderr)
            failures.append(name)
    print("SOURCE_WRITES: 0")
    print("CELL_VALUE_LOGGING: DISABLED")
    print("DATA_EXPORT: DISABLED")
    if failures:
        raise RuntimeError("SOURCE_CHECK_FAILED_" + "_".join(failures))
    print("TWO_SHEETS_READONLY: PASS")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("PROBE_FAILED: " + reason, file=sys.stderr)
        sys.exit(1)
