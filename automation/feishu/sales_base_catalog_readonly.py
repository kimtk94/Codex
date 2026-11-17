#!/usr/bin/env python3
"""Read-only, aggregate-only Feishu Sales Base table catalog diagnostic.

Does NOT provision, rename, delete, or read customer records. A complete mail
staging table alone does not make the business catalog ready for web views.
"""
from collections import Counter
import os
import sys
import urllib.parse

import qq_mail_ingest as q
from qq_mail_audit import EXPECTED_BUSINESS_TABLES
from setup_sales_web import EXPECTED_BASE

REQUIRED = frozenset(EXPECTED_BUSINESS_TABLES | {q.TABLE})

# Historical provisioning script defined these unique marker columns for
# business tables. We count only candidate matches, never output names/IDs.
SCHEMA_SIGNATURES = {
    "ACCOUNTS": frozenset({"SFDC Account ID", "Account Name", "Institution"}),
    "CONTACTS": frozenset({"SFDC Contact ID", "Contact Name KR", "Contact Name EN"}),
    "OPPORTUNITIES": frozenset({"Opportunity ID", "Amount KRW Ex VAT", "Stage"}),
    "QUOTES": frozenset({"Quote ID", "Unit", "Currency"}),
    "PROJECTS": frozenset({"Project ID", "Expected Completion Month", "Forecast Basis"}),
    "REVENUE": frozenset({"Invoice Number", "Revenue KRW Ex VAT", "Revenue Month"}),
}


def signature_counts(token, root, tables):
    """Read-only metadata scan, bounded; never emit field values or table names."""
    if len(tables) > 100:
        raise q.SafeError("CATALOG_SCHEMA_SCAN_TOO_LARGE")
    full = Counter()
    partial = Counter()
    scanned = 0
    for table in tables:
        if not table.get("table_id"):
            raise q.SafeError("CATALOG_SCHEMA_TABLE_ID_MISSING")
        path = root + "/tables/" + urllib.parse.quote(table["table_id"], safe="")
        rows = q.get_fields(token, path)
        fields = {row.get("field_name") for row in rows}
        scanned += 1
        for role, markers in SCHEMA_SIGNATURES.items():
            hits = len(fields & markers)
            if hits == len(markers):
                full[role] += 1
            elif hits >= 2:
                partial[role] += 1
    result = {"SCHEMA_TABLES_SCANNED": scanned}
    for role in sorted(SCHEMA_SIGNATURES):
        result["SCHEMA_" + role + "_EXACT_CANDIDATES"] = full[role]
        result["SCHEMA_" + role + "_PARTIAL_CANDIDATES"] = partial[role]
    return result



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
    if os.environ.get("FEISHU_CATALOG_SCAN_FIELDS", "0") == "1":
        for name, value in signature_counts(token, root, tables).items():
            print("SALES_BASE_CATALOG_" + name + "=" + str(value))
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
