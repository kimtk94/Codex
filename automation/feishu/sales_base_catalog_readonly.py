#!/usr/bin/env python3
"""Read-only, aggregate-only Feishu Sales Base table catalog diagnostic.

Does NOT provision, rename, delete, or read customer records. A complete mail
staging table alone does not make the business catalog ready for web views.
"""
from collections import Counter
import os
import sys

import qq_mail_ingest as q
from qq_mail_audit import EXPECTED_BUSINESS_TABLES
from setup_sales_web import EXPECTED_BASE

REQUIRED = frozenset(EXPECTED_BUSINESS_TABLES | {q.TABLE})


def analyze(tables):
    names = Counter(item.get("name") for item in tables)
    required_found = sum(names[name] == 1 for name in REQUIRED)
    missing = sum(names[name] == 0 for name in REQUIRED)
    duplicate = sum(names[name] > 1 for name in REQUIRED)
    unrecognized = sum(count for name, count in names.items() if name not in REQUIRED)
    invalid_metadata = sum(not item.get("name") or not item.get("table_id") for item in tables)
    result = {
        "visible_total": len(tables),
        "required_unique": required_found,
        "required_missing": missing,
        "required_duplicated": duplicate,
        "unrecognized_visible": unrecognized,
        "invalid_metadata": invalid_metadata,
        "mail_intake_count": names[q.TABLE],
    }
    if not missing and not duplicate and not invalid_metadata:
        result["status"] = "PASS"
        result["reason"] = "REQUIRED_VISIBLE"
    else:
        result["status"] = "BLOCK"
        if names[q.TABLE] == 1 and missing == len(REQUIRED) - 1 and unrecognized == 0:
            result["reason"] = "ONLY_MAIL_INTAKE_VISIBLE"
        elif unrecognized:
            result["reason"] = "CATALOG_NAME_OR_VISIBILITY_REVIEW"
        else:
            result["reason"] = "REQUIRED_TABLES_NOT_VISIBLE"
    return result


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN", "").strip() != EXPECTED_BASE:
        raise q.SafeError("CATALOG_WRONG_TARGET_BASE")
    token, root = q.auth()
    tables = q.list_all(root + "/tables", token, "catalog_list_tables")
    summary = analyze(tables)
    for name, value in summary.items():
        print("SALES_BASE_CATALOG_" + name.upper() + "=" + str(value))
    print("SALES_BASE_CATALOG_PROBE_FINISHED read_only=1 customer_values=0 writes=0")
    if summary["status"] != "PASS":
        raise q.SafeError("CATALOG_NOT_READY_" + summary["reason"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, q.SafeError) else type(exc).__name__
        print("SALES_BASE_CATALOG_PROBE_FAILED:" + detail, file=sys.stderr)
        sys.exit(1)
