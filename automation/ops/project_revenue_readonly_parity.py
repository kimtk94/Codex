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


def age_hours(now, value):
    if value is None:
        raise SafeError("PROJECT_SOURCE_TIMESTAMP_MISSING")
    delta = (now - value).total_seconds() / 3600
    if delta < -0.25:
        raise SafeError("PROJECT_SOURCE_TIMESTAMP_FUTURE")
    return max(0.0, delta)


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
    now = dt.datetime.now(dt.timezone.utc)
    snapshot_age = age_hours(now, latest_source_timestamp(source[1][1:]))
    mail_age = age_hours(now, latest_source_timestamp(source[4][1:]))
    max_feishu = float(os.environ.get("FEISHU_SNAPSHOT_MAX_AGE_HOURS", "48"))
    max_mail = float(os.environ.get("QQ_SOURCE_MAX_AGE_HOURS", "6"))
    print("PROJECT_ORIGINAL_SNAPSHOT_AGE_HOURS=" + str(round(snapshot_age, 2)))
    print("PROJECT_QQ_SOURCE_AGE_HOURS=" + str(round(mail_age, 2)))
    if snapshot_age > max_feishu or mail_age > max_mail:
        raise SafeError("PROJECT_ORIGINAL_SOURCE_STALE")
    expected = build(*source)
    sink = get(session, DST, TAB, "A1:X1000")
    stats = project_counts(expected, sink)
    for key, value in stats.items():
        print("PROJECT_PARITY_" + key + "=" + str(value))
    print("PROJECT_PARITY_SOURCE_READ_PASS writes=0 no_customer_payload=1")
    if stats["SINK_ONLY"] or stats["SOURCE_ONLY"]:
        raise SafeError("PROJECT_LIFECYCLE_SOURCE_SINK_BLOCK")
    print("PROJECT_ID_SET_PARITY_PASS lifecycle_values_not_certified=1")
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
