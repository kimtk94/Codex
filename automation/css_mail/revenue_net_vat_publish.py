#!/usr/bin/env python3
"""Publish VAT-excluded *issued* revenue from original QQ invoice evidence.

This generated tab never modifies gross Invoice, Pending, Forecast, Decision,
payment, or CRM source values. Statement VAT basis remains unverified: it is
shown separately, never silently treated as net recognized revenue.
"""
import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_UP

from tax_invoice_extract import extract
from unified_followup_sync import DST, SRC, KST, get, put, ensure
import incremental_sync as css

TAB = "BI Revenue Net VAT Monthly"
HEAD = ["Month", "Issued Invoice Gross KRW (VAT incl)",
        "Issued Net Revenue KRW (VAT excl)",
        "Issued Net Revenue kUSD @1500",
        "Issued Invoice Count",
        "Verified Pending KRW (VAT basis unverified)",
        "Forecast KRW (estimate, separate)",
        "Verified At KST", "Evidence State"]
ALLOWED = {"FILENAME_PARSED", "VERIFIED_LEGACY_FILENAME", "EXISTS_IN_LEGACY"}
REPLY = re.compile(r"^\\s*(?:re|fw|fwd|회신|답장|전달)\\s*[:：]", re.I)
NOTICE = re.compile(
    r"^\\s*❗?\\ufe0f?\\s*Notice:\\s*Invoice Issued\\s*&\\s*Statement Confirmed\\b", re.I)


def cell(row, idx):
    return str(row[idx]).strip() if len(row) > idx and row[idx] is not None else ""


def issue_month(value):
    try:
        when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError("INVALID_INVOICE_ISSUE_DATE") from err
    if when.tzinfo is None:
        raise ValueError("UNZONED_INVOICE_ISSUE_DATE")
    return when.astimezone(KST).strftime("%Y-%m")


def net_won(gross):
    """Round each invoice's tax-exclusive supply amount to whole KRW."""
    if not isinstance(gross, int) or gross <= 0:
        raise ValueError("NONPOSITIVE_INVOICE")
    return int((Decimal(gross) * Decimal(10) / Decimal(11)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))


def build(invoice_rows, monthly_rows, now):
    if not invoice_rows or cell(invoice_rows[0], 0) != "invoice_number":
        raise ValueError("ORIGINAL_INVOICE_SCHEMA_MISSING")
    if not monthly_rows or monthly_rows[0][:6] != [
        "Month", "Actual Invoice KRW", "Pending Verified KRW", "Forecast KRW",
        "Combined KRW (verified + estimate)", "Invoice Count"]:
        raise ValueError("REVENUE_LIFECYCLE_SCHEMA_MISSING")
    evidence = {}
    for row in invoice_rows[1:]:
        invoice = cell(row, 0)
        if not re.fullmatch(r"209126\\d{6}", invoice) or cell(row, 10) not in ALLOWED:
            continue
        subject = cell(row, 6)
        if REPLY.match(subject) or not NOTICE.match(subject):
            continue
        parsed = extract(cell(row, 5))
        if not parsed or parsed[4] is None or parsed[0] != invoice:
            raise ValueError("INVOICE_FILENAME_UNVERIFIED_" + invoice)
        try:
            amount = int(cell(row, 1))
        except ValueError as err:
            raise ValueError("INVOICE_AMOUNT_INVALID_" + invoice) from err
        if amount != parsed[4] or amount <= 0 or not cell(row, 8):
            raise ValueError("INVOICE_AMOUNT_UID_MISMATCH_" + invoice)
        month = issue_month(cell(row, 7))
        if month < "2026-10":
            continue
        value = (month, amount)
        if invoice in evidence and evidence[invoice] != value:
            raise ValueError("DUPLICATE_INVOICE_CONFLICT_" + invoice)
        evidence[invoice] = value

    monthly = {cell(r,0): r for r in monthly_rows[1:]
               if re.fullmatch(r"20\\d{2}-(?:0[1-9]|1[0-2])",cell(r,0))}
    if "2026-10" not in monthly:
        raise ValueError("OCTOBER_SOURCE_MISSING")
    verified = {}
    for month, amount in evidence.values():
        item = verified.setdefault(month, [0, 0, 0])
        item[0] += amount
        item[1] += net_won(amount)
        item[2] += 1
    timestamp = now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    rows = [HEAD]
    for month, record in sorted(monthly.items()):
        if month < "2026-10":
            continue
        gross, net, count = verified.get(month, [0,0,0])
        try:
            actual = int(str(cell(record,1)).replace("₩","").replace(",","").strip())
            pending = int(str(cell(record,2)).replace("₩","").replace(",","").strip())
            forecast = int(str(cell(record,3)).replace("₩","").replace(",","").strip())
            recorded_count = int(cell(record,5))
        except ValueError as err:
            raise ValueError("MONTHLY_TOTAL_FORMAT_INVALID_" + month) from err
        if actual != gross or recorded_count != count:
            raise ValueError("ISSUED_INVOICE_MONTH_PARITY_FAILED_" + month)
        if pending < 0 or forecast < 0:
            raise ValueError("NEGATIVE_PENDING_OR_FORECAST")
        if len(record) > 7 and int(cell(record,7) or 0) != 0:
            raise ValueError("UNVERIFIED_PENDING_STILL_OPEN_" + month)
        rows.append([month,gross,net,str((Decimal(net)/Decimal(1500000)).quantize(
            Decimal("0.001"),rounding=ROUND_HALF_UP)),count,pending,forecast,
            timestamp,"INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"])
    if not evidence or not rows[1:]:
        raise ValueError("NO_VERIFIED_INVOICES")
    return rows


def main():
    api = css.authorize()
    invoice = get(api, SRC, "CSS Tax Invoice Extract", "A1:L10000")
    monthly = get(api, DST, "BI Revenue Lifecycle Monthly", "A1:Q100")
    generated = build(invoice, monthly, dt.datetime.now(dt.timezone.utc))
    # Source and derived output are separate; verify readback before heartbeat.
    ensure(api, DST, TAB)
    existing = get(api, DST, TAB, "A1:I100")
    if existing and len(existing) > len(generated):
        raise ValueError("REFUSE_TO_SHRINK_NET_REVENUE_AUDIT")
    put(api, DST, TAB, "A1", generated, "RAW")
    observed = get(api, DST, TAB, "A1:I" + str(len(generated)))
    if observed != [[str(v) for v in row] for row in generated]:
        raise ValueError("REVENUE_NET_VAT_READBACK_MISMATCH")
    oct_row = next(r for r in generated if r[0] == "2026-10")
    print("NET_VAT_VERIFIED month=2026-10 invoices=" + str(oct_row[4])
          + " gross_krw=" + str(oct_row[1]) + " net_krw=" + str(oct_row[2]),
          flush=True)


if __name__ == "__main__":
    main()
