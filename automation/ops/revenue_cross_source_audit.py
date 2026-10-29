#!/usr/bin/env python3
"""Read-only Revenue integrity gate across QQ, CSS, SFDC and Feishu projections.

QQ evidence is NOT personal revenue and MUST NOT be auto-imported into Actual.
Invoice+Pending is verified billing, while Forecast and received cash are distinct.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from decimal import Decimal
from pathlib import Path
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SFDC = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QQ = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
KST = dt.timezone(dt.timedelta(hours=9))


def cell(row, i):
    return str(row[i]).strip() if i < len(row) and row[i] is not None else ""


def money(s):
    v = re.sub(r"[₩,\s]", "", str(s or "")).removesuffix("KRW")
    if not re.fullmatch(r"\d+(?:\.0+)?", v):
        raise ValueError("INVALID_FINANCIAL_AMOUNT")
    return int(Decimal(v))


def keyed(rows, number, amount, month, year="2026"):
    if not rows or any(f not in rows[0] for f in (number, amount, month)):
        raise ValueError("INVOICE_SCHEMA_MISSING")
    h = {n: i for i, n in enumerate(rows[0])}
    data = {}
    for r in rows[1:]:
        if not cell(r, h[month]).startswith(year+"-"):
            continue
        invoice = cell(r, h[number])
        if not re.fullmatch(r"\d{10,15}", invoice):
            raise ValueError("INVALID_INVOICE_ID")
        amount_krw = money(cell(r, h[amount]))
        if invoice in data and data[invoice] != amount_krw:
            raise ValueError("CONFLICTING_DUPLICATE_INVOICE")
        data[invoice] = amount_krw
    if not data:
        raise ValueError("EMPTY_INVOICE_EVIDENCE")
    return data


def verify(monthly, legacy, payments, manifest, qq, canonical, month):
    if not monthly or monthly[0][:4] != ["Month", "Actual Invoice KRW",
                                         "Pending Verified KRW", "Forecast KRW"]:
        raise ValueError("MONTHLY_REVENUE_SCHEMA_MISSING")
    current = next((r for r in monthly[1:] if cell(r, 0) == month), None)
    if not current or len(current) < 13:
        raise ValueError("MONTHLY_SOURCE_NOT_FOUND")
    actual, pending, forecast = (money(cell(current, i)) for i in (1, 2, 3))
    billing = money(cell(current, 12))
    if billing != actual+pending:
        raise ValueError("VERIFIED_BILLING_SUM_MISMATCH")
    if not legacy or not any("ACTUAL" in cell(r, 0) for r in legacy[:1]):
        raise ValueError("LEGACY_3WAY_SCHEMA_MISSING")
    legacy_amount = {}
    for r in legacy[1:]:
        key = cell(r, 0).lower()
        if key.startswith("actual ("):
            legacy_amount["actual"] = money(cell(r, 1))
        elif key.startswith("pending ("):
            legacy_amount["pending"] = money(cell(r, 1))
    if len(legacy_amount) != 2:
        raise ValueError("LEGACY_RECONCILIATION_INCOMPLETE")
    if not payments or cell(payments[0], 0) != "Payment Reconciliation QC":
        raise ValueError("PAYMENT_AUDIT_SCHEMA_MISSING")
    proof = {cell(r, 0): cell(r, 1) for r in payments[1:] if r}
    evidence = proof.get("Invoice-level verified collected KRW", "")
    if not evidence:
        raise ValueError("PAYMENT_EVIDENCE_STATUS_MISSING")
    if not manifest or cell(manifest[0], 0) != "Source":
        raise ValueError("FEISHU_SOURCE_MANIFEST_MISSING")
    source_dates = {cell(r, 0): cell(r, 1) for r in manifest[1:] if r}
    if not {"Payment Outstanding", "Payment Receipt", "eTax Invoice"}.issubset(source_dates):
        raise ValueError("FEISHU_PAYMENT_SOURCES_MISSING")
    qq_invoices = keyed(qq, "invoice_number", "amount_krw", "issued_month")
    canonical_invoices = keyed(canonical, "invoice_number", "amount_krw", "invoice_month")
    conflicts = sorted(k for k in qq_invoices.keys() & canonical_invoices.keys()
                       if qq_invoices[k] != canonical_invoices[k])
    if conflicts:
        raise ValueError("SOURCE_INVOICE_AMOUNTS_DISAGREE")
    qq_only = sorted(qq_invoices.keys()-canonical_invoices.keys())
    css_only = sorted(canonical_invoices.keys()-qq_invoices.keys())
    flags = []
    if legacy_amount["actual"] != actual or legacy_amount["pending"] != pending:
        flags.append("LEGACY_3WAY_STALE_DO_NOT_PROMOTE")
    if qq_only or css_only:
        flags.append("QQ_CSS_INVOICE_COVERAGE_REVIEW")
    if evidence.upper() == "UNKNOWN":
        flags.append("PAYMENT_PROOF_REQUIRED")
    return {
        "status": "REVIEW_REQUIRED" if flags else "PASS",
        "month": month,
        "current_invoice_krw": actual,
        "verified_pending_krw": pending,
        "verified_billing_krw": billing,
        "forecast_separate_krw": forecast,
        "legacy_invoice_krw": legacy_amount["actual"],
        "legacy_pending_krw": legacy_amount["pending"],
        "qq_invoice_evidence_count": len(qq_invoices),
        "css_canonical_invoice_count": len(canonical_invoices),
        "qq_only_count": len(qq_only),
        "qq_only_krw": sum(qq_invoices[k] for k in qq_only),
        "qq_only_ids": qq_only,
        "css_only_count": len(css_only),
        "css_only_ids": css_only,
        "payment_verified_collected": evidence if evidence.upper() == "UNKNOWN" else money(evidence),
        "feishu_payment_source_dates": source_dates,
        "flags": flags,
        "ownership_assumption": "NO_INFERENCE; source presence does not prove personal ownership",
    }


def read_book(session, book, ranges):
    endpoint = "https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values:batchGet"
    response = session.get(endpoint, params=[("ranges", a1) for a1 in ranges]+
                           [("valueRenderOption", "FORMATTED_VALUE")], timeout=60)
    response.raise_for_status()
    values = response.json().get("valueRanges", [])
    if len(values) != len(ranges):
        raise ValueError("INCOMPLETE_SHEETS_BATCH")
    return [p.get("values", []) for p in values]


def main():
    raw = os.environ.get("CKD_DRIVE_SA_JSON")
    if not raw:
        raise RuntimeError("MISSING_READONLY_SHEET_CREDENTIAL")
    cfg = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(
        cfg, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(creds)
    x = read_book(session, SFDC, [
        "'BI Revenue Lifecycle Monthly'!A1:P20",
        "'Revenue 3-Way Audit 2026-10'!A1:C9",
        "'Payment Reconciliation QC'!A1:E24",
        "'Feishu Source Manifest'!A1:G20"])
    y = read_book(session, QQ, [
        "'QQ 2026 Invoice Backfill'!A1:K3000",
        "'CSS Tax Invoice List'!A1:N1000"])
    # This legacy comparison is scoped to the 2026-10 source, even after month-end.
    report = verify(*x, *y, month="2026-10")
    out = Path("audit-results")
    out.mkdir(exist_ok=True)
    (out/"revenue-cross-source.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # Never print customer addresses or anything beyond invoice IDs and aggregate sums.
    print("REVENUE_CROSS_SOURCE_AUDIT="+json.dumps(report, ensure_ascii=False))
    if report["status"] != "PASS":
        print("REVIEW_REQUIRED: Do not add QQ-only invoices to personal Actual automatically")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as exc:
        print("REVENUE_CROSS_SOURCE_FAILED="+str(exc).split("\n")[0], file=sys.stderr)
        sys.exit(1)
