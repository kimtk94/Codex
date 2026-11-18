#!/usr/bin/env python3
"""No-write reconciliation of legacy monthly rows vs current source-derived months."""
import datetime as dt
import decimal
import sys

from project_revenue_readonly_parity import sheets_session
from revenue_lifecycle_monthly import (SRC, DST, TAB, HEAD, get, compute,
                                       reconcile_pending, cell)

INPUTS = (
    (SRC, "CSS Tax Invoice Extract", "A1:L10000", "invoice_number"),
    (DST, "BI Project Lifecycle Overview", "A1:X1000", "Project / Sub-project"),
    (SRC, "CSS Statement Amount Extract", "A1:K2000", "statement_key"),
)


def numeric(value):
    s = str(value if value is not None else "").strip().replace(",", "").replace("₩", "")
    try:
        n = decimal.Decimal(s) if s else decimal.Decimal(0)
    except decimal.InvalidOperation:
        raise RuntimeError("MONTHLY_OLD_ROW_NON_NUMERIC")
    if not n.is_finite() or n < 0:
        raise RuntimeError("MONTHLY_OLD_ROW_INVALID_AMOUNT")
    return n


def month_index(rows):
    if not rows or rows[0] != HEAD:
        raise RuntimeError("MONTHLY_OLD_HEADER_INVALID")
    out = {}
    for row in rows[1:]:
        month = cell(row, 0)
        if not month or month in out:
            raise RuntimeError("MONTHLY_OLD_MONTH_DUPLICATE_OR_MISSING")
        out[month] = row
    return out


def old_only_status(row):
    # Never retire any month containing an issued Invoice or verified/unverified
    # pending; a suppressed month could hide actual Revenue or unpaid balance.
    protected = (1, 2, 5, 6, 7, 9)
    if any(numeric(cell(row, col)) > 0 for col in protected):
        return "FINANCIAL_PROOF_PRESENT_BLOCK"
    # This row had only a forecast, which is not an actual Revenue record.
    if numeric(cell(row, 3)) > 0 or numeric(cell(row, 8)) > 0:
        return "FORECAST_ONLY_SAFE_RETIRE_CANDIDATE"
    return "ALL_ZERO_OR_EMPTY_SAFE_RETIRE_CANDIDATE"


def compare_existing(old, new):
    indexed, fresh = month_index(old), month_index(new)
    missing = sorted(set(indexed) - set(fresh))
    added = sorted(set(fresh) - set(indexed))
    result = {
        "old_month_count": len(indexed),
        "new_month_count": len(fresh),
        "old_only": len(missing),
        "new_only": len(added),
        "overlap": len(set(fresh) & set(indexed)),
        "old_only_protected": 0,
        "old_only_forecast_only": 0,
        "old_only_zero": 0,
    }
    for key in missing:
        category = old_only_status(indexed[key])
        if category.startswith("FINANCIAL_"):
            result["old_only_protected"] += 1
        elif category.startswith("FORECAST_ONLY"):
            result["old_only_forecast_only"] += 1
        else:
            result["old_only_zero"] += 1
    return result


def main():
    s = sheets_session()
    sources = []
    for book, tab, area, header in INPUTS:
        rows = get(s, book, tab, area)
        if not rows or not rows[0] or rows[0][0] != header:
            raise RuntimeError("MONTHLY_CANONICAL_SOURCE_UNAVAILABLE")
        sources.append(rows)
    old = get(s, DST, TAB, "A1:L100")
    derived = compute(sources[0], sources[1], dt.datetime.now(dt.timezone.utc))
    reconcile_pending(sources[2], sources[0], sources[1], derived)
    stats = compare_existing(old, derived)
    for key, count in sorted(stats.items()):
        print("MONTHLY_FORECAST_PLAN_" + key.upper() + "=" + str(count))
    print("MONTHLY_FORECAST_PLAN_NO_WRITES=1 confirmed_invoice_months_preserved=1")
    if stats["old_only_protected"]:
        raise RuntimeError("MONTHLY_HISTORICAL_PROOF_BLOCK")
    print("MONTHLY_FORECAST_PLAN_SAFE_RETIRE_ONLY=1")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("MONTHLY_FORECAST_PLAN_BLOCK=" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
