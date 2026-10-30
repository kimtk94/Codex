#!/usr/bin/env python3
"""Show which Revenue monthly sources are authoritative vs stale snapshots.

Reads original finance sources; only writes to a distinct generated audit tab.
Does not change existing invoice, financial, forecast, customer, or decision rows.
"""
import datetime as dt
import re

from unified_followup_sync import DST, SRC, KST, get, put, ensure
import incremental_sync as css

TAB = "Revenue Source Authority"
HEAD = ["Month", "Source Tab", "Source Role", "Issued Invoice Count",
        "Amount KRW", "Tax Basis", "Source Parity", "Authoritative For KPI",
        "Verified KST", "Required Action"]


def cell(row, i):
    return str(row[i]).strip() if i < len(row) and row[i] is not None else ""


def krw(value):
    raw = str(value or "").replace(",", "").replace("₩", "").replace(" KRW", "").strip()
    if not re.fullmatch(r"-?\d+", raw):
        raise ValueError("UNVERIFIED_AMOUNT")
    return int(raw)


def month_row(rows, month):
    for r in rows[1:]:
        if cell(r, 0) == month:
            return r
    return None


def emit(rows, month, name, role, count, amount, tax, parity, allowed, now, action):
    rows.append([month, name, role, count, amount, tax, parity, allowed,
                 now, action])


def build(monthly, net, historical, legacy, completeness, now, month="2026-10"):
    if monthly[0][:2] != ["Month", "Actual Invoice KRW"] or (
        net[0][:3] != ["Month", "Issued Invoice Gross KRW (VAT incl)",
                       "Issued Net Revenue KRW (VAT excl)"]):
        raise ValueError("CANONICAL_REVENUE_SCHEMA_MISSING")
    live = month_row(monthly, month)
    verified = month_row(net, month)
    if not live or not verified:
        raise ValueError("CURRENT_MONTH_INVOICE_SOURCE_MISSING")
    gross, count = krw(cell(live, 1)), krw(cell(live, 5))
    net_gross, net_amount, net_count = (
        krw(cell(verified, 1)), krw(cell(verified, 2)), krw(cell(verified, 4)))
    if (gross < 0 or count < 0 or net_amount < 0 or net_amount > gross
        or net_gross != gross or net_count != count
        or cell(verified, 8) != "INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"):
        raise ValueError("CANONICAL_INVOICE_VAT_PARITY_FAILED")
    when = now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    result = [HEAD]
    emit(result, month, "BI Revenue Lifecycle Monthly", "CANONICAL_ACTUAL_GROSS",
         count, gross, "VAT_INCLUDED", "MATCHED_TO_NET_AUDIT", "YES", when,
         "Use only for VAT-inclusive billed invoice totals; not cash collected")
    emit(result, month, "BI Revenue Net VAT Monthly", "CANONICAL_ISSUED_NET",
         count, net_amount, "VAT_EXCLUDED", "MATCHED_TO_INVOICE_SOURCE", "YES", when,
         "Use for VAT-exclusive issued revenue; not cash collected")

    legacy_checks = []
    if historical and cell(historical[0], 0).startswith("2026-10 ACTUAL"):
        row = next((r for r in historical[1:]
                    if cell(r, 0) == "Actual (issued invoice)"), None)
        if row:
            amount = krw(cell(row, 1))
            marker = re.search(r"(\d+) original invoice", cell(row, 2))
            n = int(marker.group(1)) if marker else "UNKNOWN"
            legacy_checks.append(("Revenue 3-Way Audit 2026-10", n, amount))
    if legacy and legacy[0][:2] == ["invoice_month", "invoice_count"]:
        item = month_row(legacy, month)
        if item:
            legacy_checks.append(("CSS Invoice Monthly Summary",
                                  krw(cell(item, 1)), krw(cell(item, 3))))
    for name, n, amount in legacy_checks:
        same = n == count and amount == gross
        emit(result, month, name, "LEGACY_SNAPSHOT", n, amount, "VAT_INCLUDED",
             "MATCHED_BUT_NOT_CANONICAL" if same else "STALE_SOURCE_DO_NOT_USE",
             "NO", when, "Keep historical source read-only; use canonical VAT-labeled KPI")
    if completeness and cell(completeness[0], 0).startswith("TAX INVOICE COMPLETENESS"):
        row = next((r for r in completeness[1:]
                    if cell(r, 0) == "October invoice count"), None)
        if row:
            n = krw(cell(row, 1))
            emit(result, month, "Tax Invoice Completeness Audit",
                 "LEGACY_COUNT_ONLY", n, "UNKNOWN", "VAT_UNKNOWN",
                 "MATCHED_BUT_NOT_CANONICAL" if n == count else "STALE_SOURCE_DO_NOT_USE",
                 "NO", when, "Do not use prior-day count as the live invoice total")
    if not legacy_checks:
        emit(result, month, "Legacy Revenue Sources", "LEGACY_NOT_READ",
             "UNKNOWN", "UNKNOWN", "VAT_UNKNOWN", "REVIEW_REQUIRED", "NO", when,
             "Historical snapshots were not found; check source availability")
    return result


def main():
    api = css.authorize()
    monthly = get(api, DST, "BI Revenue Lifecycle Monthly", "A1:Q100")
    net = get(api, DST, "BI Revenue Net VAT Monthly", "A1:I100")
    legacy_three = get(api, DST, "Revenue 3-Way Audit 2026-10", "A1:C30")
    legacy_css = get(api, SRC, "CSS Invoice Monthly Summary", "A1:P30")
    legacy_count = get(api, DST, "Tax Invoice Completeness Audit", "A1:C20")
    generated = build(monthly, net, legacy_three, legacy_css, legacy_count,
                      dt.datetime.now(dt.timezone.utc))
    current = get(api, DST, TAB, "A1:J30") if True else []
    if current and current[0] != HEAD:
        raise ValueError("REFUSE_TO_OVERWRITE_FOREIGN_AUTHORITY_TAB")
    ensure(api, DST, TAB)
    put(api, DST, TAB, "A1", generated, "RAW")
    actual = get(api, DST, TAB, "A1:J" + str(len(generated)))
    if len(actual) != len(generated) or actual[0] != HEAD:
        raise ValueError("AUTHORITY_READBACK_MISMATCH")
    for expected, observed in zip(generated[1:], actual[1:]):
        for idx in (0, 1, 2, 5, 6, 7, 8, 9):
            if cell(observed, idx) != str(expected[idx]):
                raise ValueError("AUTHORITY_READBACK_ROW_MISMATCH")
    statuses = [r for r in generated[1:] if r[6] == "STALE_SOURCE_DO_NOT_USE"]
    print(f"REVENUE_AUTHORITY_CHECK month=2026-10 canonical_count={generated[1][3]} "
          f"legacy_stale_source_count={len(statuses)} published=YES")


if __name__ == "__main__":
    main()
