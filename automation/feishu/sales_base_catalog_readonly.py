#!/usr/bin/env python3
"""Read-only, aggregate-only Feishu Sales Base table catalog diagnostic.

Does NOT provision, rename, delete, or read customer records. A complete mail
staging table alone does not make the business catalog ready for web views.
"""
from collections import Counter
import hashlib
import os
import sys
import urllib.parse

import qq_mail_ingest as q
from qq_mail_audit import EXPECTED_BUSINESS_TABLES
from setup_sales_web import EXPECTED_BASE

REQUIRED = frozenset(EXPECTED_BUSINESS_TABLES | {q.TABLE})

# Immutable SHA-256 digests of Feishu *table IDs* observed in two distinct
# SUCCESS 2026-11-05 native-web configuration runs:
# https://github.com/kimtk94/Codex/actions/runs/42025405631
# https://github.com/kimtk94/Codex/actions/runs/42060114237
# The two runs had identical IDs for all seven roles and the expected Base.
# Never log the actual table IDs or newly observed names.
HISTORIC_TABLE_ID_SHA256 = {
    "ACCOUNTS": "b34f2b96fa52211e999fd7cc0abe657c0f9e08859021099a0a260e30f2c968ca",
    "CONTACTS": "2139515e64cfe6f0f89a846063cebd2b5d42ce28135c9c23955fa3e6bc2fc1d0",
    "OPPORTUNITIES": "4831bdc6ffbfee91d0f4bac9cc21ccd77588cad16046d944827cb554d720266a",
    "QUOTES": "d81d1c488cba871a1719b5a56963433112e2255e7a5500f67cc31aedb2f81ca6",
    "PROJECTS": "3785d45535fcdcf3f563e56c4e350632e4b2c2af6a96d593da407fb01f2f1ffb",
    "REVENUE": "ce51ab8fec45a0c2f7b01ff95c015c63d18d761941dee71b4a73e73a52a9c2b1",
    "MAIL": "3794738f453c4faf3f047c7d020adb15b22a0f71955a8581e3b7ac6708233c96",
}

EXPECTED_ROLE_NAMES = {
    "ACCOUNTS": "Accounts",
    "CONTACTS": "Contacts",
    "OPPORTUNITIES": "Opportunities",
    "QUOTES": "Quotes",
    "PROJECTS": "Projects",
    "REVENUE": "Revenue",
    "MAIL": q.TABLE,
}


def historic_table_identity(tables):
    """Compare preserved historical IDs, not names; aggregate only.

    NOT_VISIBLE can mean deletion, access filtering or an absent catalog
    response. It is never treated as proof that an underlying table was deleted.
    """
    seen = {}
    for item in tables:
        table_id = item.get("table_id")
        if not table_id:
            raise q.SafeError("HISTORIC_CATALOG_TABLE_ID_MISSING")
        fingerprint = hashlib.sha256(table_id.encode("utf-8")).hexdigest()
        if fingerprint in seen:
            raise q.SafeError("HISTORIC_CATALOG_DUPLICATE_TABLE_ID")
        seen[fingerprint] = item.get("name")

    result = {}
    summary = Counter()
    for role, fingerprint in HISTORIC_TABLE_ID_SHA256.items():
        if fingerprint not in seen:
            status = "NOT_VISIBLE"
        elif seen[fingerprint] == EXPECTED_ROLE_NAMES[role]:
            status = "PRESENT_SAME_NAME"
        else:
            status = "PRESENT_CHANGED_NAME"
        result["HISTORIC_" + role + "_STATUS"] = status
        summary[status] += 1

    for status in ("PRESENT_SAME_NAME", "PRESENT_CHANGED_NAME", "NOT_VISIBLE"):
        result["HISTORIC_" + status + "_COUNT"] = summary[status]
    return result


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
    for name, value in historic_table_identity(tables).items():
        print("SALES_BASE_CATALOG_" + name + "=" + str(value))
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
