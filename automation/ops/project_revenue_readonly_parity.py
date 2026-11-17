#!/usr/bin/env python3
"""Read-only Project Lifecycle and VAT-exclusive Revenue source/sink parity.

Reads verified Google Sheets and Feishu rows using the existing production
validation code. Does not call project/Revenue writers, does not expose project
IDs or invoice values, and does not infer paid state from a Feishu flag.
Run separately with PARITY_DOMAIN=project or revenue in GitHub Actions.
"""
import datetime as dt
import os
import sys
import inspect
import collections
import re
from decimal import Decimal, InvalidOperation

from qq_mail_ingest import SafeError, auth, list_all
from sales_metrics_sync import (EXPECTED_BASE, SCHEMAS, equivalent, raw_value,
                                sheets_session, table_catalog, table_path)
from monthly_revenue_actual_sync import (
    read_canonical_sources, index_records, validate_mail_only_existing,
)
from project_lifecycle_refresh import (
    SRC, DST, TAB, HEAD, build, get, latest_source_timestamp,
)


def project_counts(new, old):
    """Compare immutable X project keys, not row order or customer fields."""
    if not old or old[0] not in (HEAD, HEAD[:22], HEAD[:20]):
        raise SafeError("PROJECT_SINK_HEADER_UNVERIFIED")
    if not new or new[0] != HEAD:
        raise SafeError("PROJECT_COMPUTED_HEADER_UNVERIFIED")
    def index(rows):
        keys = [str(row[0]).strip().upper() for row in rows[1:] if row and str(row[0]).strip()]
        if len(keys) != len(rows) - 1 or len(set(keys)) != len(keys):
            raise SafeError("PROJECT_DUPLICATE_OR_BLANK_X")
        return set(keys)
    source_keys = index(new)
    sink_keys = index(old)
    return {
        "SOURCE_PROJECTS": len(source_keys),
        "SINK_PROJECTS": len(sink_keys),
        "SINK_ONLY": len(sink_keys - source_keys),
        "SOURCE_ONLY": len(source_keys - sink_keys),
        "MATCHED_PROJECTS": len(source_keys & sink_keys),
    }


# Stable source-owned project fields; skip customer identities and manual
# overrides, and do not publish the underlying X IDs or differences.
PROJECT_STATUS_FIELDS = (5, 6, 7, 10, 11, 12)
PROJECT_FINANCE_FIELDS = (14, 15, 16, 20, 22, 23)


def comparable_project_value(value):
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    try:
        amount = Decimal(text.replace(",", ""))
        if amount.is_finite():
            return ("NUMERIC", amount)
    except (InvalidOperation, ValueError):
        pass
    return ("TEXT", text)


def project_value_counts(new, old):
    """Compare status/issued/pending values only across common verified keys."""
    if not new or not old or old[0] != HEAD or new[0] != HEAD:
        raise SafeError("PROJECT_VALUE_PARITY_FULL_SCHEMA_REQUIRED")
    src = {str(row[0]).strip().upper(): row for row in new[1:]}
    dst = {str(row[0]).strip().upper(): row for row in old[1:]}
    matched = set(src) & set(dst)
    changes_status = 0
    changes_finance = 0
    for key in matched:
        a, b = src[key], dst[key]
        if any(comparable_project_value(a[i] if len(a) > i else "") !=
               comparable_project_value(b[i] if len(b) > i else "")
               for i in PROJECT_STATUS_FIELDS):
            changes_status += 1
        if any(comparable_project_value(a[i] if len(a) > i else "") !=
               comparable_project_value(b[i] if len(b) > i else "")
               for i in PROJECT_FINANCE_FIELDS):
            changes_finance += 1
    return {
        "STATUS_MISMATCHED_PROJECTS": changes_status,
        "FINANCE_MISMATCHED_PROJECTS": changes_finance,
        "CHECKED_PROJECTS": len(matched),
    }


PROJECT_FIELD_LABELS = {
    5: "FEISHU_STATUS", 6: "CSS_STAGE", 7: "CSS_PROGRESS",
    10: "REMAINING_TAT", 11: "EXPECTED_COMPLETION",
    12: "EXPECTED_REVENUE_MONTH", 14: "ISSUED_INVOICE_COUNT",
    15: "ISSUED_AMOUNT_KRW", 16: "BILLING_CLASS",
    20: "OPEN_STATEMENTS", 22: "PENDING_VERIFIED_AMOUNT",
    23: "PENDING_EVIDENCE",
}


def project_field_differences(new, old):
    if not new or not old or old[0] != HEAD or new[0] != HEAD:
        raise SafeError("PROJECT_FIELD_DIFF_FULL_SCHEMA_REQUIRED")
    source = {str(r[0]).strip().upper(): r for r in new[1:]}
    sink = {str(r[0]).strip().upper(): r for r in old[1:]}
    counts = {label: 0 for label in PROJECT_FIELD_LABELS.values()}
    for project_id in source.keys() & sink.keys():
        a, b = source[project_id], sink[project_id]
        for index, label in PROJECT_FIELD_LABELS.items():
            av = a[index] if len(a) > index else ""
            bv = b[index] if len(b) > index else ""
            if comparable_project_value(av) != comparable_project_value(bv):
                counts[label] += 1
    return counts


# Count semantic date changes separately from text-format changes. The expected
# completion field represents a calendar day, not a billing or payment date.
# Unparseable date formats remain unverified; do not call them equivalent.
DATE_REVIEW_CATEGORIES = ("RAW_EQUAL", "FORMAT_ONLY", "DIFFERENT_CALENDAR_DAY",
                          "SOURCE_BLANK", "SINK_BLANK", "UNPARSEABLE")


def parse_expected_day(value):
    raw = str(value if value is not None else "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{5}(?:\.0+)?", raw):
        serial = int(Decimal(raw))
        if 40000 <= serial <= 60000:
            return dt.date(1899, 12, 30) + dt.timedelta(days=serial)
        return None
    if re.fullmatch(r"20\d{2}[01]\d[0-3]\d", raw):
        try:
            return dt.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None
    if re.fullmatch(r"20\d{2}[-/.][01]\d[-/.][0-3]\d", raw):
        try:
            return dt.date.fromisoformat(raw.replace("/", "-").replace(".", "-"))
        except ValueError:
            return None
    # Timestamp with explicit offset: normalize to project's local KST day.
    if re.fullmatch(r"20\d{2}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d)", raw):
        try:
            val = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return val.astimezone(dt.timezone(dt.timedelta(hours=9))).date()
        except ValueError:
            return None
    # Naive timestamp is assumed a local calendar date; no UTC conversion.
    if re.fullmatch(r"20\d{2}[-/.]\d\d[-/.]\d\d[T ]\d\d:\d\d(?::\d\d)?", raw):
        try:
            return dt.date.fromisoformat(raw[:10].replace("/", "-").replace(".", "-"))
        except ValueError:
            return None
    return None


def date_review_status(source, sink):
    a = str(source if source is not None else "").strip()
    b = str(sink if sink is not None else "").strip()
    if a == b:
        return "RAW_EQUAL"
    if not a:
        return "SOURCE_BLANK"
    if not b:
        return "SINK_BLANK"
    ad, bd = parse_expected_day(a), parse_expected_day(b)
    if ad is None or bd is None:
        return "UNPARSEABLE"
    return "FORMAT_ONLY" if ad == bd else "DIFFERENT_CALENDAR_DAY"


BILLING_CATEGORIES = ("ISSUED_PENDING", "ISSUED_UNVERIFIED", "STATEMENT_PENDING",
                      "COMPLETED_UNVERIFIED", "BLOCKED", "FORECAST",
                      "UNKNOWN", "BLANK")


def billing_category(value):
    raw = str(value or "").strip().upper()
    if not raw:
        return "BLANK"
    if raw.startswith("ISSUED + STATEMENT PENDING"):
        return "ISSUED_PENDING"
    if raw.startswith("ISSUED (BALANCE UNVERIFIED)"):
        return "ISSUED_UNVERIFIED"
    if raw.startswith("STATEMENT READY - INVOICE PENDING"):
        return "STATEMENT_PENDING"
    if raw.startswith("COMPLETED - STATEMENT NOT VERIFIED"):
        return "COMPLETED_UNVERIFIED"
    if raw.startswith("BLOCKED / EXCLUDED FROM FORECAST"):
        return "BLOCKED"
    if raw.startswith("PROJECT FORECAST"):
        return "FORECAST"
    return "UNKNOWN"


def project_semantic_triage(source_rows, sink_rows):
    """Aggregate only, no project IDs, customer fields, dates or amounts logged."""
    if not source_rows or not sink_rows or source_rows[0] != HEAD or sink_rows[0] != HEAD:
        raise SafeError("PROJECT_TRIAGE_FULL_SCHEMA_REQUIRED")
    source = {str(r[0]).strip().upper(): r for r in source_rows[1:]}
    sink = {str(r[0]).strip().upper(): r for r in sink_rows[1:]}
    days = {name: 0 for name in DATE_REVIEW_CATEGORIES}
    billing = collections.Counter()
    financial = collections.Counter()
    for key in source.keys() & sink.keys():
        a, b = source[key], sink[key]
        days[date_review_status(a[11] if len(a)>11 else "",
                                b[11] if len(b)>11 else "")] += 1
        src_bill = a[16] if len(a)>16 else ""
        sink_bill = b[16] if len(b)>16 else ""
        if comparable_project_value(src_bill) != comparable_project_value(sink_bill):
            before, after = billing_category(sink_bill), billing_category(src_bill)
            billing[before + "_TO_" + after] += 1
        # Amount comparison is aggregate direction only, never raw money.
        for index, label in ((14, "INVOICE_COUNT"), (15, "ISSUED_AMOUNT"),
                             (22, "VERIFIED_PENDING")):
            src = comparable_project_value(a[index] if len(a)>index else "")
            dst = comparable_project_value(b[index] if len(b)>index else "")
            if src == dst:
                continue
            if (isinstance(src, tuple) and isinstance(dst, tuple) and
                    src[0] == "NUMERIC" and dst[0] == "NUMERIC"):
                direction = "UP" if src[1] > dst[1] else "DOWN"
            elif src == "" and dst != "":
                direction = "SOURCE_EMPTY"
            elif src != "" and dst == "":
                direction = "SINK_EMPTY"
            else:
                direction = "OTHER"
            financial[label + "_" + direction] += 1
    return days, billing, financial



DATE_SHIFT_BANDS = ((1, "1D"), (7, "2_TO_7D"),
                    (30, "8_TO_30D"), (None, "31_PLUS_D"))


def project_date_shift_triage(source_rows, sink_rows):
    """Aggregate calendar shift magnitude for the Feishu forecast completion DATE."""
    if not source_rows or not sink_rows or source_rows[0] != HEAD or sink_rows[0] != HEAD:
        raise SafeError("PROJECT_DATE_SHIFT_FULL_SCHEMA_REQUIRED")
    src = {str(r[0]).strip().upper(): r for r in source_rows[1:]}
    dst = {str(r[0]).strip().upper(): r for r in sink_rows[1:]}
    out = collections.Counter()
    for key in src.keys() & dst.keys():
        a, b = src[key], dst[key]
        computed = a[11] if len(a) > 11 else ""
        stored = b[11] if len(b) > 11 else ""
        if date_review_status(computed, stored) != "DIFFERENT_CALENDAR_DAY":
            continue
        x, y = parse_expected_day(computed), parse_expected_day(stored)
        if x is None or y is None:
            raise SafeError("PROJECT_DATE_SHIFT_UNVERIFIED")
        shift_days = (x - y).days
        magnitude = abs(shift_days)
        band = next(label for upper, label in DATE_SHIFT_BANDS
                    if upper is None or magnitude <= upper)
        direction = "EXPECTED_LATER" if shift_days > 0 else "EXPECTED_EARLIER"
        out[direction + "_" + band] += 1
        out["DATE_SHIFTS_TOTAL"] += 1
    return out


def project_forecast_date_alignment(source_rows, sink_rows, feishu_rows):
    """Read-only provenance of changed lifecycle completion dates.

    Lifecycle output column 11 is the DATE from Feishu forecast column 10.
    BI Project Month Control and source forecast column 11 determine the
    projected MONTH in lifecycle output column 12, not the date.
    """
    if not source_rows or not sink_rows or source_rows[0] != HEAD or sink_rows[0] != HEAD:
        raise SafeError("FEISHU_ALIGNMENT_FULL_SCHEMA_REQUIRED")
    source = {str(r[0]).strip().upper(): r for r in source_rows[1:]}
    sink = {str(r[0]).strip().upper(): r for r in sink_rows[1:]}
    feishu = {}
    for r in feishu_rows[1:]:
        if len(r) > 1 and str(r[1]).strip():
            x = str(r[1]).strip().upper()
            if x in feishu:
                raise SafeError("FEISHU_DUPLICATE_SUBPROJECT_IN_DATE_ALIGNMENT")
            feishu[x] = r
    report = collections.Counter()
    for project in source.keys() & sink.keys():
        row_a, row_b = source[project], sink[project]
        computed = row_a[11] if len(row_a) > 11 else ""
        stored = row_b[11] if len(row_b) > 11 else ""
        if date_review_status(computed, stored) != "DIFFERENT_CALENDAR_DAY":
            continue
        if project not in feishu:
            report["FEISHU_SUBPROJECT_NOT_FOUND"] += 1
            continue
        source_forecast = feishu[project][10] if len(feishu[project]) > 10 else ""
        if not str(source_forecast if source_forecast is not None else "").strip():
            report["FEISHU_FORECAST_BLANK"] += 1
            continue
        forecast = parse_expected_day(source_forecast)
        if forecast is None:
            report["FEISHU_FORECAST_UNPARSEABLE"] += 1
            continue
        if forecast == parse_expected_day(computed):
            report["SOURCE_FORECAST_MATCHES_RECALCULATED_DATE"] += 1
        elif forecast == parse_expected_day(stored):
            report["STORED_DATE_MATCHES_FORECAST"] += 1
        else:
            report["SOURCE_AND_STORED_DIFFER_FROM_FORECAST"] += 1
    return report




def age_hours(now, value):
    if value is None:
        raise SafeError("PROJECT_SOURCE_TIMESTAMP_MISSING")
    delta = (now - value).total_seconds() / 3600
    if delta < -0.25:
        raise SafeError("PROJECT_SOURCE_TIMESTAMP_FUTURE")
    return max(0.0, delta)


def compute_lifecycle(source, previous):
    """Match the lifecycle implementation's required prior-QQ-only context.

    PR #802 adds previous_rows for an independently verified source-only X
    that just transitioned from pending Statement to issued Invoice. Omitting
    previous_rows would create a false 111->110 regression in an audit.
    """
    if "previous_rows" in inspect.signature(build).parameters:
        print("PROJECT_LIFECYCLE_PREVIOUS_CONTEXT=APPLIED", flush=True)
        return build(*source, previous_rows=previous)
    print("PROJECT_LIFECYCLE_PREVIOUS_CONTEXT=NOT_SUPPORTED_BY_MAIN", flush=True)
    return build(*source)


def project_audit():
    session = sheets_session()  # Google readonly OAuth scope
    specs = [
        (SRC, "CSS Project Dashboard", "A1:AK1000", "exclude"),
        (DST, "Feishu Project TAT Forecast", "A1:Q2000", "Snapshot KST"),
        (SRC, "CSS Tax Invoice Extract", "A1:L10000", "invoice_number"),
        (DST, "BI Project Month Control", "A1:K2000", "Sub-Project Number"),
        (SRC, "CSS Git Ingest", "F:Q", "received_at"),
        (SRC, "CSS Statement Amount Extract", "A1:K2000", "statement_key"),
    ]
    source = []
    for book, title, bounds, first in specs:
        rows = get(session, book, title, bounds)
        if not rows or not rows[0] or rows[0][0] != first:
            raise SafeError("PROJECT_SOURCE_HEADER_INVALID")
        source.append(rows)
    tat_header = source[1][0]
    if (len(tat_header) <= 11 or
            tat_header[10] != "Forecast Completion Date" or
            tat_header[11] != "Forecast Completion Month"):
        raise SafeError("PROJECT_TAT_DATE_MONTH_COLUMN_MAPPING_UNVERIFIED")
    print("PROJECT_TAT_DATE_MONTH_COLUMN_MAPPING_PASS date_col=10 month_col=11")
    if HEAD[11] != "Feishu Expected Completion" or HEAD[12] != "Expected Revenue Month":
        raise SafeError("PROJECT_OUTPUT_DATE_MONTH_COLUMN_MAPPING_UNVERIFIED")
    print("PROJECT_OUTPUT_DATE_MONTH_COLUMN_MAPPING_PASS date_col=11 month_col=12")
    now = dt.datetime.now(dt.timezone.utc)
    snapshot_age = age_hours(now, latest_source_timestamp(source[1][1:]))
    mail_age = age_hours(now, latest_source_timestamp(source[4][1:]))
    max_feishu = float(os.environ.get("FEISHU_SNAPSHOT_MAX_AGE_HOURS", "48"))
    max_mail = float(os.environ.get("QQ_SOURCE_MAX_AGE_HOURS", "6"))
    print("PROJECT_ORIGINAL_SNAPSHOT_AGE_HOURS=" + str(round(snapshot_age, 2)))
    print("PROJECT_QQ_SOURCE_AGE_HOURS=" + str(round(mail_age, 2)))
    if snapshot_age > max_feishu or mail_age > max_mail:
        raise SafeError("PROJECT_ORIGINAL_SOURCE_STALE")
    sink = get(session, DST, TAB, "A1:X1000")
    if not sink or sink[0] not in (HEAD, HEAD[:22], HEAD[:20]):
        raise SafeError("PROJECT_SINK_HEADER_UNVERIFIED")
    expected = compute_lifecycle(source, sink)
    stats = project_counts(expected, sink)
    for key, value in stats.items():
        print("PROJECT_PARITY_" + key + "=" + str(value))
    print("PROJECT_PARITY_SOURCE_READ_PASS writes=0 no_customer_payload=1")
    if stats["SINK_ONLY"] or stats["SOURCE_ONLY"]:
        raise SafeError("PROJECT_LIFECYCLE_SOURCE_SINK_BLOCK")
    print("PROJECT_ID_SET_PARITY_PASS")
    content = project_value_counts(expected, sink)
    for key, value in content.items():
        print("PROJECT_PARITY_" + key + "=" + str(value))
    by_field = project_field_differences(expected, sink)
    for name, count in sorted(by_field.items()):
        print("PROJECT_PARITY_FIELD_" + name + "_DIFF=" + str(count))
    date_states, billing_states, finance_states = project_semantic_triage(expected, sink)
    for label, count in date_states.items():
        print("PROJECT_TRIAGE_EXPECTED_DAY_" + label + "=" + str(count))
    for label, count in sorted(billing_states.items()):
        print("PROJECT_TRIAGE_BILLING_" + label + "=" + str(count))
    for label, count in sorted(finance_states.items()):
        print("PROJECT_TRIAGE_FINANCE_" + label + "=" + str(count))
    shifts = project_date_shift_triage(expected, sink)
    for name, count in sorted(shifts.items()):
        print("PROJECT_TRIAGE_DAY_SHIFT_" + name + "=" + str(count))
    if shifts["DATE_SHIFTS_TOTAL"] != date_states["DIFFERENT_CALENDAR_DAY"]:
        raise SafeError("PROJECT_DATE_SHIFT_ACCOUNTING_MISMATCH")
    alignment = project_forecast_date_alignment(expected, sink, source[1])
    for name, count in sorted(alignment.items()):
        print("PROJECT_TRIAGE_FEISHU_ALIGNMENT_" + name + "=" + str(count))
    aligned_count = sum(alignment.values())
    if aligned_count != shifts["DATE_SHIFTS_TOTAL"]:
        raise SafeError("PROJECT_DATE_ALIGNMENT_ACCOUNTING_MISMATCH")
    print("PROJECT_TRIAGE_AGGREGATES_ONLY raw_customer_values=0 writes=0")
    if content["STATUS_MISMATCHED_PROJECTS"] or content["FINANCE_MISMATCHED_PROJECTS"]:
        raise SafeError("PROJECT_LIFECYCLE_FIELD_PARITY_BLOCK")
    print("PROJECT_SOURCE_FIELD_PARITY_PASS latest_original_source_age_checked=1")
    return stats


def month_counts(desired, existing):
    """Compare canonical issued months; historical older months may remain."""
    validate_mail_only_existing(existing)
    idx = index_records(existing)
    keys = [row.get("Source Key") for row in desired]
    if not all(keys) or len(set(keys)) != len(keys):
        raise SafeError("MONTHLY_CANONICAL_DUPLICATE_OR_EMPTY_KEY")
    missing = [key for key in keys if key not in idx]
    changed = [row for row in desired if row["Source Key"] in idx
               and not equivalent(idx[row["Source Key"]].get("fields") or {}, row)]
    return {
        "CANONICAL_MONTHS": len(desired),
        "SINK_ROWS": len(existing),
        "MISSING_CANONICAL_MONTHS": len(missing),
        "DIFFERING_CANONICAL_MONTHS": len(changed),
        "MATCHED_CANONICAL_MONTHS": len(desired) - len(missing) - len(changed),
        "PRESERVED_OTHER_MONTHS": len(set(idx) - set(keys)),
    }


def revenue_audit():
    if os.environ.get("FEISHU_BASE_APP_TOKEN", "") != EXPECTED_BASE:
        raise SafeError("REVENUE_WRONG_FEISHU_BASE")
    desired = read_canonical_sources()  # 3 independent Sheets, readonly
    token, root = auth()
    catalog = table_catalog(token, root)
    ids = catalog.get("Monthly Tax Invoice") or []
    if len(ids) != 1:
        raise SafeError("REVENUE_SINK_TABLE_MISSING_OR_DUPLICATE")
    path = table_path(root, ids[0])
    fields = {row.get("field_name"): row.get("type")
              for row in list_all(path + "/fields", token, "revenue_schema_read")}
    if any(fields.get(name) != kind for name, kind in SCHEMAS["Monthly Tax Invoice"]):
        raise SafeError("REVENUE_SINK_SCHEMA_DRIFT")
    existing = list_all(path + "/records", token, "revenue_monthly_readback")
    stats = month_counts(desired, existing)
    for key, value in stats.items():
        print("REVENUE_PARITY_" + key + "=" + str(value))
    print("REVENUE_PARITY_READ_ONLY writes=0 vat_included_and_excluded_separate=1 "
          "pending_forecast_excluded=1 original_QQ_full_coverage=UNVERIFIED")
    if stats["MISSING_CANONICAL_MONTHS"] or stats["DIFFERING_CANONICAL_MONTHS"]:
        raise SafeError("REVENUE_CANONICAL_SOURCE_SINK_BLOCK")
    print("REVENUE_CANONICAL_SOURCE_SINK_PARITY_PASS "
          "original_QQ_full_coverage=UNVERIFIED")
    return stats


def main():
    domain = os.environ.get("PARITY_DOMAIN", "").lower().strip()
    if domain == "project":
        project_audit()
    elif domain == "revenue":
        revenue_audit()
    else:
        raise SafeError("PARITY_DOMAIN_INVALID")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("PROJECT_REVENUE_READONLY_PROBE_BLOCK:" + reason, file=sys.stderr)
        sys.exit(1)
