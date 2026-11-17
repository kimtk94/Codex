#!/usr/bin/env python3
"""Read-only verification of historical Feishu table IDs against direct field APIs.

No records, customers or quotation values are read; only Feishu metadata status
is logged. Historical IDs were extracted from two 2026-11-05 successful
native-web setup logs in this repository and checked against their SHA256
fingerprints in sales_base_catalog_readonly.py.
"""
import hashlib
import os
import sys
import urllib.parse

import qq_mail_ingest as q
from sales_base_catalog_readonly import HISTORIC_TABLE_ID_SHA256
from setup_sales_web import EXPECTED_BASE

# Table IDs are resource locators, not authentication credentials. They are not
# printed to public workflow logs. The same IDs occurred in 11/05 action URLs.
HISTORIC_IDS = {
    "ACCOUNTS": "tbl6yptwb2n1msqd",
    "CONTACTS": "tblgK35xTKQiQR94",
    "OPPORTUNITIES": "tbljEs3xlif2cMJP",
    "QUOTES": "tblaFDb2DZRJjCxy",
    "PROJECTS": "tblKPQPrLf4Udpta",
    "REVENUE": "tbl9x6220E2Hex59",
    "MAIL": "tblcdgy23HiO1s2L",
}
# Only classify codes that the Feishu API explicitly returned. Even a
# TableIdNotFound response is not definitive proof of irreversible deletion.
NOT_FOUND_CODES = {"1254041", "1254004"}
PERMISSION_CODES = {"1254302"}


def validate_ids():
    if set(HISTORIC_IDS) != set(HISTORIC_TABLE_ID_SHA256):
        raise q.SafeError("HISTORIC_ID_ROLE_MISMATCH")
    for role, table_id in HISTORIC_IDS.items():
        if hashlib.sha256(table_id.encode("utf-8")).hexdigest() != HISTORIC_TABLE_ID_SHA256[role]:
            raise q.SafeError("HISTORIC_ID_FINGERPRINT_MISMATCH")


def classify_error(reason):
    reason = str(reason)
    if "_CODE_" in reason:
        code = reason.rsplit("_CODE_", 1)[1]
        if code in NOT_FOUND_CODES:
            return "API_TABLE_ID_NOT_FOUND"
        if code in PERMISSION_CODES:
            return "API_PERMISSION_DENIED"
    if "_HTTP_403" in reason:
        return "HTTP_PERMISSION_OR_POLICY"
    if "_HTTP_404" in reason:
        return "HTTP_NOT_FOUND_OR_ROUTE"
    return "OTHER_API_ERROR"


def probe_field_metadata(token, root):
    result = {}
    for role, table_id in HISTORIC_IDS.items():
        path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
        try:
            fields = q.get_fields(token, path)
            result[role] = "API_FIELDS_ACCESSIBLE" if fields else "API_FIELDS_EMPTY"
        except q.SafeError as exc:
            result[role] = classify_error(exc)
    return result


def main():
    validate_ids()
    if os.environ.get("FEISHU_BASE_APP_TOKEN", "").strip() != EXPECTED_BASE:
        raise q.SafeError("HISTORIC_DIRECT_PROBE_WRONG_BASE")
    token, root = q.auth()
    outcomes = probe_field_metadata(token, root)
    for role in sorted(outcomes):
        print("HISTORIC_TABLE_DIRECT_" + role + "=" + outcomes[role])
    print("HISTORIC_TABLE_DIRECT_PROBE_FINISHED requests=" + str(len(outcomes)) +
          " read_only=1 record_reads=0 writes=0")
    if outcomes.get("MAIL") != "API_FIELDS_ACCESSIBLE":
        raise q.SafeError("HISTORIC_MAIL_CONTROL_INACCESSIBLE")
    if any(outcomes.get(role) != "API_FIELDS_ACCESSIBLE" for role in HISTORIC_IDS if role != "MAIL"):
        raise q.SafeError("HISTORIC_BUSINESS_TABLES_DIRECT_ACCESS_BLOCK")
    print("HISTORIC_BUSINESS_TABLES_DIRECT_ACCESS_PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, q.SafeError) else type(exc).__name__
        print("HISTORIC_TABLE_DIRECT_PROBE_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
