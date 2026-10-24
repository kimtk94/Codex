#!/usr/bin/env python3
"""Read all records from three approved Feishu Base tables, without exporting customer data."""
import collections
import os
import sys
import urllib.parse

from base_readonly_probe import request, require
from payment_table_audit import list_pages

TARGETS = ("Payment Outstanding 10.20", "eTax-Invoice", "Online-Project")
KNOWN_ONLINE_PROJECT_ID = "tblZGzTAZ7oPWL7L"

def main():
    auth = request("POST", "/open-apis/auth/v3/tenant_access_token/internal",
                   body={"app_id": require("FEISHU_APP_ID"),
                         "app_secret": require("FEISHU_APP_SECRET")})
    if auth.get("code") != 0 or not auth.get("tenant_access_token"):
        raise RuntimeError("AUTH_FAILED")
    token = auth["tenant_access_token"]
    app_token = require("FEISHU_BASE_APP_TOKEN")
    prefix = "/open-apis/bitable/v1/apps/" + urllib.parse.quote(app_token, safe="")
    print("AUTH: PASS", flush=True)
    tables = list(list_pages(prefix + "/tables", token))
    print("BASE_TABLE_COUNT:", len(tables), flush=True)
    missing = []
    for name in TARGETS:
        matches = [t for t in tables if t.get("name") == name]
        if len(matches) != 1:
            print("TABLE_MISSING:", name, "MATCHES:", len(matches), flush=True)
            missing.append(name)
            continue
        table_id = matches[0].get("table_id")
        if not table_id:
            raise RuntimeError("MISSING_TABLE_ID")
        if name == "Online-Project" and table_id != KNOWN_ONLINE_PROJECT_ID:
            raise RuntimeError("ONLINE_PROJECT_ID_MISMATCH")
        root = prefix + "/tables/" + urllib.parse.quote(table_id, safe="")
        fields = list(list_pages(root + "/fields", token))
        records = list(list_pages(root + "/records", token))
        ids = [r.get("record_id") for r in records]
        if not all(ids) or len(set(ids)) != len(ids):
            raise RuntimeError("DUPLICATE_OR_EMPTY_RECORD_ID")
        # Validate records are available in memory. Never print or save customer values.
        counts = collections.Counter(str(f.get("type")) for f in fields)
        print("TABLE_READ_PASS:", name, "ID:", table_id,
              "FIELDS:", len(fields), "RECORDS:", len(records),
              "FIELD_TYPES:", dict(sorted(counts.items())), flush=True)
    print("BASE_WRITES: 0", flush=True)
    print("CUSTOMER_VALUE_LOGGING: DISABLED", flush=True)
    print("DATA_EXPORT: DISABLED", flush=True)
    if missing:
        raise RuntimeError("MISSING_TARGET_TABLES_" + str(len(missing)))
    print("THREE_TABLE_READONLY: PASS", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Existing library handles API requests, but avoid printing raw exceptions/response.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if not reason.startswith(("MISSING_TARGET_TABLES_", "AUTH_FAILED", "MISSING_TABLE_ID",
                                  "ONLINE_PROJECT_ID_MISMATCH", "DUPLICATE_OR_EMPTY_RECORD_ID",
                                  "Missing GitHub Actions secret")):
            reason = type(exc).__name__ if not isinstance(exc, RuntimeError) else "BASE_API_ERROR"
        print("THREE_TABLE_READONLY_FAILED:", reason, file=sys.stderr)
        sys.exit(1)
