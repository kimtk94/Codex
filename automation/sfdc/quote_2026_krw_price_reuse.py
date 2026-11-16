#!/usr/bin/env python3
"""2026 KRW-only historical SFDC process-price candidate selector.

Only original, approved KRW process-level prices may enter this index.
2025 prices, converted USD, invoice amounts, and Quote totals never become
process unit prices. Inputs must arrive from a verified PRIVATE pricing source.
This module NEVER writes Salesforce; do not print private candidate records to CI.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

SOURCE_KIND = "VERIFIED_SFDC_KRW_PROCESS_PRICE"
YEAR = 2026
PROCESS_RX = re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
QUOTE_RX = re.compile(r"^QID-[0-9-]{8,50}$")
ACCOUNT_RX = re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
CONTACT_RX = re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
ALLOWED_UNITS = {"G raw data", "Gb", "M raw reads", "K tags", "Lane",
                 "Cell", "K Reads", "K Clean Reads", "NA", "sample"}
# Only these two labels have a verified equivalence; no conversions to reads.
def canonical_unit(value):
    raw = str(value or "").strip()
    return "Gb" if raw in {"Gb", "G raw data"} else raw

def _decimal(value):
    if isinstance(value, bool):
        return None
    s = str("" if value is None else value).strip().replace(",", "")
    if not s:
        return None
    try:
        v = Decimal(s)
        return v if v.is_finite() and 0 <= v <= Decimal("999999999") else None
    except InvalidOperation:
        return None

def _native_id(value, rx):
    s = str(value or "").strip()
    if not rx.fullmatch(s):
        return ""
    # 15-character prefix is stable for matching a 15- and 18-char Salesforce ID.
    return s[:15]

def _valid_year(value):
    s = str(value or "").strip()
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").year == YEAR
    except ValueError:
        return False

def _valid_reference(row):
    """Strict fail-closed gate, never infer currency/approval from name or price."""
    if row.get("source_kind") != SOURCE_KIND or row.get("source_verified") is not True:
        return "UNVERIFIED_SOURCE"
    if row.get("currency") != "KRW" or row.get("was_usd_converted") is not False:
        return "NOT_NATIVE_KRW"
    if row.get("vat_basis") != "VAT_EXCLUDED":
        return "VAT_BASIS_UNVERIFIED"
    if not _valid_year(row.get("created_date")):
        return "OUTSIDE_2026"
    if row.get("approval_status") != "APPROVED" or row.get("active") is not True:
        return "NOT_APPROVED_ACTIVE"
    if not QUOTE_RX.fullmatch(str(row.get("quote_id") or "")):
        return "QUOTE_ID_UNVERIFIED"
    if not _native_id(row.get("account_id"), ACCOUNT_RX):
        return "ACCOUNT_ID_UNVERIFIED"
    if not _native_id(row.get("contact_id"), CONTACT_RX):
        return "CONTACT_003_UNVERIFIED"
    if not PROCESS_RX.fullmatch(str(row.get("process_id") or "")):
        return "PROCESS_ID_UNVERIFIED"
    if not isinstance(row.get("product_signature"), str) or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}", row["product_signature"]):
        return "PRODUCT_SIGNATURE_UNVERIFIED"
    if canonical_unit(row.get("data_unit")) not in ALLOWED_UNITS:
        return "PROCESS_DATA_UNIT_UNVERIFIED"
    if _decimal(row.get("unit_price_krw")) is None:
        return "PROCESS_KRW_PRICE_MISSING"
    if canonical_unit(row.get("data_unit")) != "NA" and _decimal(row.get("data_size")) is None:
        return "DATA_SIZE_MISSING"
    if not isinstance(row.get("sample_quantity"), int) or not (1 <= row["sample_quantity"] <= 1000000):
        return "SAMPLE_QUANTITY_MISSING"
    return "PASS"

def choose_price_references(request, records, limit=10):
    """Rank original 2026 KRW process prices without auto-applying any rate.

    1. Same verified Account + Contact; 2. same Account/different Contact;
    3. other customer, exact Product signature + Process + unit.
    Production-amount and sample-quantity exact matches are ranked above
    different sizes, but latter remain COMPARISON_ONLY.
    """
    if not isinstance(records, list) or not isinstance(request, dict):
        raise ValueError("INVALID_INPUT")
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("INVALID_LIMIT")
    req_process = str(request.get("process_id") or "")
    req_product = str(request.get("product_signature") or "")
    req_unit = canonical_unit(request.get("data_unit"))
    req_account = _native_id(request.get("account_id"), ACCOUNT_RX)
    req_contact = _native_id(request.get("contact_id"), CONTACT_RX)
    req_size = _decimal(request.get("data_size"))
    req_qty = request.get("sample_quantity")
    if not PROCESS_RX.fullmatch(req_process) or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}", req_product):
        return {"status": "HOLD_PRODUCT_PROCESS_UNVERIFIED", "candidates": [],
                "rejections": {}, "price_auto_apply": False, "crm_writes": 0}
    if req_unit not in ALLOWED_UNITS or (req_size is None and req_unit != "NA") or not isinstance(req_qty, int) or req_qty < 1:
        return {"status": "HOLD_PRODUCTION_UNIT_OR_QTY", "candidates": [],
                "rejections": {}, "price_auto_apply": False, "crm_writes": 0}
    counts = Counter()
    candidates = []
    for row in records:
        reason = _valid_reference(row) if isinstance(row, dict) else "INVALID_RECORD"
        if reason != "PASS":
            counts[reason] += 1
            continue
        if row["process_id"] != req_process or row["product_signature"] != req_product:
            counts["OTHER_PRODUCT_PROCESS"] += 1
            continue
        if canonical_unit(row["data_unit"]) != req_unit:
            counts["UNIT_MISMATCH"] += 1
            continue
        row_account = _native_id(row["account_id"], ACCOUNT_RX)
        row_contact = _native_id(row["contact_id"], CONTACT_RX)
        if req_account and req_contact and row_account == req_account and row_contact == req_contact:
            tier = "SAME_ACCOUNT_CONTACT"
            rank = 0
        elif req_account and row_account == req_account:
            tier = "SAME_ACCOUNT_OTHER_CONTACT"
            rank = 1
        else:
            tier = "OTHER_CUSTOMER_SAME_PRODUCT_PROCESS"
            rank = 2
        size_match = req_size is not None and _decimal(row["data_size"]) == req_size
        qty_match = row["sample_quantity"] == req_qty
        comparison_only = tier != "SAME_ACCOUNT_CONTACT" or not (size_match and qty_match)
        candidates.append({
            "tier": tier, "quote_id": row["quote_id"], "created_date": row["created_date"],
            "account_id": row["account_id"], "contact_id": row["contact_id"],
            "unit_price_krw": str(_decimal(row["unit_price_krw"])),
            "currency": "KRW", "vat_basis": "VAT_EXCLUDED",
            "process_id": row["process_id"], "product_signature": row["product_signature"],
            "data_unit": req_unit, "data_size": row["data_size"],
            "sample_quantity": row["sample_quantity"], "size_match": size_match,
            "quantity_match": qty_match, "comparison_only": comparison_only,
            "requires_record_approval": True, "price_auto_apply": False,
            "_sort": (rank, not size_match, not qty_match, -int(row["created_date"][:10].replace("-", "")))
        })
    candidates.sort(key=lambda c: c["_sort"])
    for c in candidates:
        del c["_sort"]
    return {
        "status": "CANDIDATES_NEED_USER_APPROVAL" if candidates else "NO_2026_KRW_MATCH",
        "candidates": candidates[:limit],
        "total_matching_candidates": len(candidates),
        "rejections": dict(sorted(counts.items())),
        "price_auto_apply": False, "crm_writes": 0
    }

def audit_existing_report():
    """Verify QQ raw report and prove whether it contains a native KRW line price.

    Do not treat 'Unit Price USD' as original KRW, even if Created Date is 2026.
    Log only aggregate health; NEVER publish customer prices or IDs.
    """
    from oppo_quote_popular_patterns import (EXPECTED_QUOTE, EXPECTED_OPP, EXPECTED_AUDIT,
        OPP_TAB, QUOTE_TAB, AUDIT_TAB, normalize_matrix, verify_mail_audit, read_live_matrix)
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    import os
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        return {"source_integrity": "SOURCE_UNAVAILABLE", "price_status": "HOLD_NO_NATIVE_KRW_PROCESS_SOURCE",
                "crm_writes": 0}
    cred = service_account.Credentials.from_service_account_info(json.loads(raw),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    sess = AuthorizedSession(cred)
    matrices = {"opportunities": normalize_matrix(read_live_matrix(sess, OPP_TAB, "A1:O2000"), EXPECTED_OPP),
                "quotation": normalize_matrix(read_live_matrix(sess, QUOTE_TAB, "A1:Y6000"), EXPECTED_QUOTE)}
    _, _, audit = normalize_matrix(read_live_matrix(sess, AUDIT_TAB, "A1:J30"), EXPECTED_AUDIT)
    evidence = verify_mail_audit(matrices, audit)
    headers, _, rows = matrices["quotation"]
    year_rows = [r for r in rows if _valid_year(
        _date_to_iso(r.get("Created Date")))]
    # Explicit native KRW price column is mandatory; a total, converted field,
    # Opportunity Amount, invoice, or USD field cannot satisfy this gate.
    native_cols = {"Unit Price KRW", "Process Unit Price KRW"}
    available = sorted(native_cols.intersection(headers))
    return {"source_integrity": "PASS_HASH_VERIFIED",
            "price_status": "HOLD_KRW_PRICE_SOURCE_NOT_APPROVED" if available else "HOLD_NO_NATIVE_KRW_PROCESS_SOURCE",
            "source": "SFDC_EMAIL_QUOTATION_RAW",
            "year": YEAR, "source_process_rows": len(rows),
            "year_process_rows": len(year_rows),
            "native_krw_unit_columns": len(available),
            "verified_krw_price_rows": 0,
            "state": evidence["quotation"]["state"],
            "crm_writes": 0}

def _date_to_iso(value):
    s = str(value or "").strip()
    try:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return s[:10]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-live", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.audit_live:
        parser.error("Only --audit-live supported. Use choose_price_references() in authenticated private context.")
    try:
        result = audit_existing_report()
    except Exception:
        result = {"source_integrity": "SOURCE_UNAVAILABLE", "price_status": "HOLD_NO_NATIVE_KRW_PROCESS_SOURCE",
                  "crm_writes": 0}
    output = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output+"\n")
    print(output)

if __name__ == "__main__":
    main()
