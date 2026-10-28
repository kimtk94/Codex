#!/usr/bin/env python3
"""Fail-closed reconciliation of verified QQ historical evidence vs CSS invoice list."""
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SHEET = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
YEAR = os.getenv("BACKFILL_YEAR", "2026")

def load_rows(session, tab, bound):
    address = urllib.parse.quote("'" + tab + "'!A1:N" + str(bound), safe="")
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + SHEET + "/values/" + address
    response = session.get(url, timeout=70)
    response.raise_for_status()
    rows = response.json().get("values", [])
    if not rows:
        raise RuntimeError("EMPTY_SOURCE_" + tab)
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(str(v).strip() for v in row)]

def money(raw):
    normalized = re.sub(r"[^0-9.-]", "", str(raw or ""))
    if not normalized:
        raise ValueError("EMPTY_INVOICE_AMOUNT")
    value = float(normalized)
    if not value.is_integer() or value < 0:
        raise ValueError("INVALID_INVOICE_AMOUNT")
    return int(value)

def index(rows, number_field, amount_field, year_field):
    data, collisions = {}, []
    for row in rows:
        inv = str(row.get(number_field, "")).strip()
        month = str(row.get(year_field, "")).strip()
        if not month.startswith(YEAR + "-"):
            continue
        if not re.fullmatch(r"\d{10,15}", inv):
            raise ValueError("INVALID_INVOICE_NUMBER: " + inv[-5:])
        amount = money(row.get(amount_field))
        if inv in data and data[inv] != amount:
            collisions.append(inv)
        data[inv] = amount
    return data, collisions

def main():
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    session = AuthorizedSession(credentials)
    evidence = load_rows(session, "QQ 2026 Invoice Backfill", 10000)
    canonical = load_rows(session, "CSS Tax Invoice List", 2000)
    a, a_conflict = index(evidence, "invoice_number", "amount_krw", "issued_month")
    b, b_conflict = index(canonical, "invoice_number", "amount_krw", "invoice_month")
    missing_in_css = sorted(set(a) - set(b))
    missing_in_qq = sorted(set(b) - set(a))
    mismatch = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    result = {
        "year": YEAR, "qq_evidence": len(a), "css_invoices": len(b),
        "missing_in_css": len(missing_in_css), "missing_in_qq": len(missing_in_qq),
        "amount_mismatch": len(mismatch),
        "duplicate_amount_conflicts": len(a_conflict) + len(b_conflict),
        "examples": {
            "missing_in_css": missing_in_css[:12],
            "missing_in_qq": missing_in_qq[:12],
            "amount_mismatch": mismatch[:12],
        },
    }
    print("QQ_CSS_INVOICE_PARITY " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not a or not b or any((missing_in_css, missing_in_qq, mismatch, a_conflict, b_conflict)):
        print("QQ_CSS_INVOICE_PARITY_FAILED", file=sys.stderr)
        return 2
    print("QQ_CSS_INVOICE_PARITY_PASS")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("QQ_CSS_INVOICE_PARITY_ERROR " + type(exc).__name__ + ": " + str(exc)[:200], file=sys.stderr)
        sys.exit(1)
