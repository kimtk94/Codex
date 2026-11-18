#!/usr/bin/env python3
"""Read-only, privacy-safe full 24-column lifecycle raw readback diagnostic.

Exactly reproduces the writer's expected build using the existing preserved
lifecycle context, then compares Google Sheets UNFORMATTED_VALUE GET with
the generated 24-column result. Reports aggregate mismatch categories only.
Never prints a Project X/AMEA identifier, customer name, field content or price.
"""
import collections
import decimal
import os
import sys

from project_lifecycle_refresh import (HEAD, DST, TAB, SRC, get, build,
                                       lifecycle_unformatted_readback,
                                       lifecycle_content_equal)
from project_revenue_readonly_parity import sheets_session, project_counts

NUMERIC_FIELDS = frozenset({
    "CSS Progress %", "Sample Count", "Feishu Remaining TAT Days",
    "Invoice Count", "Invoice Actual KRW", "Estimated KRW (existing)",
    "Pending KRW Verified",
})
SOURCE_SPECS = (
    (SRC, "CSS Project Dashboard", "A1:AK1000", "exclude"),
    (DST, "Feishu Project TAT Forecast", "A1:Q2000", "Snapshot KST"),
    (SRC, "CSS Tax Invoice Extract", "A1:L10000", "invoice_number"),
    (DST, "BI Project Month Control", "A1:K2000", "Sub-Project Number"),
    (SRC, "CSS Git Ingest", "F:Q", "received_at"),
    (SRC, "CSS Statement Amount Extract", "A1:K2000", "statement_key"),
)


def normalized_number(value):
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        amount = decimal.Decimal(text)
    except decimal.InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def classify(left, right, col):
    """Do not declare equivalence for identifiers, dates or text values."""
    a = "" if left is None else str(left)
    b = "" if right is None else str(right)
    if a == b:
        return "EXACT"
    field = HEAD[col]
    if field in NUMERIC_FIELDS:
        av, bv = normalized_number(left), normalized_number(right)
        if av is not None and bv is not None and av == bv:
            return "NUMERIC_REPRESENTATION_ONLY"
    if a.strip() == b.strip():
        return "WHITESPACE_ONLY"
    if not a or not b:
        return "BLANK_DIFFERENCE"
    return "TRUE_VALUE_DIFFERENCE"


def mismatch_summary(expected, observed):
    summary = collections.Counter()
    if not isinstance(expected, list) or not isinstance(observed, list):
        raise RuntimeError("READBACK_NOT_LIST")
    summary["EXPECTED_ROWS"] = max(0, len(expected) - 1)
    summary["RAW_ROWS"] = max(0, len(observed) - 1)
    summary["ROW_COUNT_MATCH"] = int(len(expected) == len(observed))
    if not expected or not observed:
        return summary
    summary["HEADER_EQUAL"] = int(expected[0] == observed[0])
    if summary["HEADER_EQUAL"] == 0:
        return summary
    for i in range(1, min(len(expected), len(observed))):
        a, b = expected[i], observed[i]
        if not isinstance(a, list) or not isinstance(b, list):
            raise RuntimeError("READBACK_ROW_TYPE_INVALID")
        if len(a) > len(HEAD) and any(v is not None and str(v).strip() for v in a[len(HEAD):]):
            raise RuntimeError("EXPECTED_EXTRA_COLUMNS_NOT_EMPTY")
        if len(b) > len(HEAD) and any(v is not None and str(v).strip() for v in b[len(HEAD):]):
            raise RuntimeError("READBACK_EXTRA_COLUMNS_NOT_EMPTY")
        row_changed = False
        for column in range(len(HEAD)):
            left = a[column] if column < len(a) else ""
            right = b[column] if column < len(b) else ""
            result = classify(left, right, column)
            if result != "EXACT":
                summary["COLUMN_" + str(column) + "_" + result] += 1
                summary[result] += 1
                row_changed = True
        if row_changed:
            summary["ROWS_WITH_ANY_MISMATCH"] += 1
    return summary


def audit():
    session = sheets_session()  # Sheets read-only OAuth scope
    sources = []
    for book, tab, area, expected_header in SOURCE_SPECS:
        rows = get(session, book, tab, area)
        if not rows or not rows[0] or rows[0][0] != expected_header:
            raise RuntimeError("LIFECYCLE_SOURCE_HEADER_MISMATCH")
        sources.append(rows)
    previous = get(session, DST, TAB, "A1:X1000")
    if not previous or previous[0] != HEAD:
        raise RuntimeError("LIFECYCLE_FORMATTED_SINK_HEADER_MISMATCH")
    expected = build(*sources, previous_rows=previous)
    project_ids = project_counts(expected, previous)
    print("LIFECYCLE_PROJECT_SOURCE=" + str(project_ids["SOURCE_PROJECTS"]))
    print("LIFECYCLE_PROJECT_SINK=" + str(project_ids["SINK_PROJECTS"]))
    print("LIFECYCLE_PROJECT_SINK_ONLY=" + str(project_ids["SINK_ONLY"]))
    print("LIFECYCLE_PROJECT_SOURCE_ONLY=" + str(project_ids["SOURCE_ONLY"]))
    if project_ids["SINK_ONLY"] or project_ids["SOURCE_ONLY"]:
        raise RuntimeError("LIFECYCLE_PROJECT_SET_NOT_STABLE")
    observed = lifecycle_unformatted_readback(session, DST, TAB,
                                              "A1:X" + str(len(expected)))
    report = mismatch_summary(expected, observed)
    report["WRITER_EXACT_CHECK"] = int(lifecycle_content_equal(expected, observed))
    for key, value in sorted(report.items()):
        print("LIFECYCLE_RAW_AUDIT_" + key + "=" + str(value))
    print("LIFECYCLE_RAW_AUDIT_NO_WRITES=1 fields_checked=24 records_private=1")
    if report["ROW_COUNT_MATCH"] != 1 or report["HEADER_EQUAL"] != 1:
        raise RuntimeError("LIFECYCLE_RAW_SCHEMA_BLOCK")
    actual = report["TRUE_VALUE_DIFFERENCE"] + report["BLANK_DIFFERENCE"]
    if actual:
        raise RuntimeError("LIFECYCLE_RAW_ACTUAL_VALUE_BLOCK")
    if report["NUMERIC_REPRESENTATION_ONLY"] or report["WHITESPACE_ONLY"]:
        print("LIFECYCLE_READBACK_CANONICALIZATION_NEEDED=1")
    else:
        print("LIFECYCLE_READBACK_CANONICALIZATION_NEEDED=0")
    print("LIFECYCLE_RAW_VALUES_SEMANTIC_PARITY_PASS=1")


if __name__ == "__main__":
    try:
        audit()
    except Exception as exc:
        print("LIFECYCLE_RAW_DIAGNOSTIC_BLOCK=" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
