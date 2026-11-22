#!/usr/bin/env python3
"""Fail-closed reconciliation of verified QQ historical evidence vs CSS invoice list."""
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

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
            raise ValueError("INVALID_INVOICE_NUMBER")
        amount = money(row.get(amount_field))
        if inv in data and data[inv] != amount:
            collisions.append(inv)
        data[inv] = amount
    return data, collisions

def summarize(evidence, canonical, extracted):
    """Count source scope gaps without publishing customer/invoice identifiers."""
    a, a_conflict = index(evidence, "invoice_number", "amount_krw", "issued_month")
    b, b_conflict = index(canonical, "invoice_number", "amount_krw", "invoice_month")
    missing_in_css = set(a) - set(b)
    missing_in_qq = set(b) - set(a)
    mismatch = {key for key in set(a) & set(b) if a[key] != b[key]}
    qq_month = {str(row.get("invoice_number", "")).strip(): str(row.get("issued_month", "")).strip()
                for row in evidence if str(row.get("issued_month", "")).startswith(YEAR + "-")}
    css_month = {str(row.get("invoice_number", "")).strip(): str(row.get("invoice_month", "")).strip()
                 for row in canonical if str(row.get("invoice_month", "")).startswith(YEAR + "-")}
    missing_months = Counter(qq_month.get(key, "UNKNOWN") for key in missing_in_css)
    missing_reverse_months = Counter(css_month.get(key, "UNKNOWN") for key in missing_in_qq)
    qq_provenance = {str(row.get("invoice_number", "")).strip(): str(row.get("evidence", "")).strip()
                     for row in evidence if str(row.get("issued_month", "")).startswith(YEAR + "-")}
    missing_provenance = Counter(qq_provenance.get(key, "UNKNOWN") for key in missing_in_css)

    extracted_index = {}
    duplicate_extract_numbers = set()
    for row in extracted:
        invoice = str(row.get("invoice_number", "")).strip()
        if not invoice or invoice not in missing_in_css:
            continue
        if invoice in extracted_index:
            duplicate_extract_numbers.add(invoice)
        else:
            extracted_index[invoice] = row
    extract_overlap = 0
    extract_amount_match = 0
    extract_amount_conflict = 0
    extract_status_counts = Counter()
    source_by_invoice = {
        str(item.get("invoice_number", "")).strip(): item
        for item in evidence
        if str(item.get("issued_month", "")).startswith(YEAR + "-")
    }
    # Matching an invoice number and gross amount is not enough to post Revenue.
    # Preserve separate lineage checks for project, contract, PO and mailbox UID.
    identity_fields = (
        ("project_id", "amea_project_id", "project_id"),
        ("h_project_id", "h_project_id", "h_project_number"),
        ("po_reference", "po_reference", "po_reference"),
        ("imap_uid", "imap_uid", "imap_uid"),
    )
    identity_match = Counter()
    identity_conflict = Counter()
    identity_missing = Counter()
    fully_matching = 0
    for invoice in missing_in_css:
        if invoice not in extracted_index:
            continue
        extract_overlap += 1
        row = extracted_index[invoice]
        extract_status_counts[str(row.get("validation_status", "")) or "UNSPECIFIED"] += 1
        source_row = source_by_invoice.get(invoice, {})
        all_fields_match = True
        for label, q_field, e_field in identity_fields:
            left = str(source_row.get(q_field, "")).strip().upper()
            right = str(row.get(e_field, "")).strip().upper()
            if not left or not right:
                identity_missing[label] += 1
                all_fields_match = False
            elif left != right:
                identity_conflict[label] += 1
                all_fields_match = False
            else:
                identity_match[label] += 1
        if all_fields_match:
            fully_matching += 1
        try:
            amount = money(row.get("amount_krw"))
        except ValueError:
            extract_amount_conflict += 1
        else:
            if amount == a[invoice]:
                extract_amount_match += 1
            else:
                extract_amount_conflict += 1

    result = {
        "year": YEAR,
        "qq_evidence": len(a), "css_invoices": len(b),
        "missing_in_css": len(missing_in_css), "missing_in_qq": len(missing_in_qq),
        "amount_mismatch": len(mismatch),
        "duplicate_amount_conflicts": len(a_conflict) + len(b_conflict),
        "qq_latest_invoice_month": max(qq_month.values(), default=None),
        "css_latest_invoice_month": max(css_month.values(), default=None),
        "missing_in_css_by_month": dict(sorted(missing_months.items())),
        "missing_in_qq_by_month": dict(sorted(missing_reverse_months.items())),
        "missing_in_css_evidence_types": dict(sorted(missing_provenance.items())),
        "extract_crosscheck": {
            "source": "CSS Tax Invoice Extract (derived view; not independent original proof)",
            "found": extract_overlap, "amount_matches": extract_amount_match,
            "amount_conflicts": extract_amount_conflict,
            "not_found": len(missing_in_css) - extract_overlap,
            "duplicate_numbers": len(duplicate_extract_numbers),
            "validation_statuses": dict(sorted(extract_status_counts.items())),
            "identity_fields_matching": dict(sorted(identity_match.items())),
            "identity_fields_conflicting": dict(sorted(identity_conflict.items())),
            "identity_fields_unavailable": dict(sorted(identity_missing.items())),
            "all_four_lineage_fields_matching": fully_matching,
            "original_mail_verified": False,
        },
        "scope_warning": "A QQ-only key is not proof of an unpaid invoice. Verify original notice, UID and downstream ledger lineage before posting revenue.",
    }
    failed = bool(not a or not b or missing_in_css or missing_in_qq or mismatch
                  or a_conflict or b_conflict or extract_amount_conflict
                  or duplicate_extract_numbers or identity_conflict)
    return result, failed


def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    session = AuthorizedSession(credentials)
    evidence = load_rows(session, "QQ 2026 Invoice Backfill", 10000)
    canonical = load_rows(session, "CSS Tax Invoice List", 2000)
    # Read-only auxiliary evidence, never used to insert rows or infer payments.
    extracted = load_rows(session, "CSS Tax Invoice Extract", 2000)
    result, failed = summarize(evidence, canonical, extracted)
    print("QQ_CSS_INVOICE_PARITY " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    if failed:
        print("QQ_CSS_INVOICE_PARITY_FAILED", file=sys.stderr)
        return 2
    print("QQ_CSS_INVOICE_PARITY_PASS")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("QQ_CSS_INVOICE_PARITY_ERROR " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
