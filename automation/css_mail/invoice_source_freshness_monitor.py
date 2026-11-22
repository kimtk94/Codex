#!/usr/bin/env python3
"""Read-only QQ/CSS invoice source-to-sink freshness monitor.

This module deliberately does NOT modify Sheets, Revenue, Tax Invoice, or CRM.
Raw invoice identifiers, names, email addresses and monetary amounts are used
only in memory and are never included in logs or the aggregate JSON artifact.
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

YEAR = os.getenv("BACKFILL_YEAR", "2026")
MAX_AGE_HOURS = 36


def timestamp(value):
    try:
        v = dt.datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
        if v.tzinfo is None:
            raise ValueError("naive")
        return v.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        raise ValueError("SOURCE_TIMESTAMP_INVALID") from None


def newest_audit(audits, now):
    if not audits or not {"year", "status", "last_run_utc"}.issubset(audits[0]):
        raise ValueError("BACKFILL_AUDIT_SCHEMA_UNAVAILABLE")
    matching = [x for x in audits if str(x.get("year", "")) == YEAR]
    if not matching:
        raise ValueError("BACKFILL_YEAR_NOT_FOUND")
    pairs = [(timestamp(x.get("last_run_utc")), x) for x in matching]
    scanned, row = max(pairs, key=lambda x: x[0])
    if str(row.get("status", "")) != "SCAN_COMPLETE":
        raise ValueError("BACKFILL_SCAN_INCOMPLETE")
    delta = (now - scanned).total_seconds() / 3600
    if delta < -5 / 60:
        raise ValueError("BACKFILL_CLOCK_SKEW")
    return scanned, delta


def indexed(rows, required, label):
    if not rows or not required.issubset(rows[0]):
        raise ValueError(label + "_SCHEMA_UNAVAILABLE")
    result = {}
    for x in rows:
        number = str(x.get("invoice_number", "")).strip()
        if not number:
            continue
        if not re.fullmatch(r"\d{10,15}", number):
            raise ValueError(label + "_INVOICE_NUMBER_INVALID")
        if number in result:
            raise ValueError(label + "_DUPLICATE_NUMBER_REVIEW")
        result[number] = x
    if not result:
        raise ValueError(label + "_NO_ROWS")
    return result


def summarize(qq_rows, css_rows, extract_rows, audits, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("VERIFICATION_CLOCK_NAIVE")
    now = now.astimezone(dt.timezone.utc)
    qq = indexed(qq_rows, {"invoice_number", "issued_month", "amount_krw"}, "QQ")
    css = indexed(css_rows, {"invoice_number", "invoice_month", "amount_krw"}, "CSS")
    extracts = indexed(extract_rows,
                       {"invoice_number", "received_at", "extracted_at_utc",
                        "validation_status", "ingest_key"}, "EXTRACT")
    scanned, age_hours = newest_audit(audits, now)

    qq_year = {k for k, v in qq.items()
               if str(v.get("issued_month", "")).startswith(YEAR + "-")}
    css_year = {k for k, v in css.items()
                if str(v.get("invoice_month", "")).startswith(YEAR + "-")}
    # Exact IDs in another period or with a blank month still count as
    # "present in source"; never label those as an entirely missing invoice.
    all_known = set(qq) | set(css)
    extract_unlinked = [x for k, x in extracts.items() if k not in all_known]
    before_scan = []
    after_scan = []
    for row in extract_unlinked:
        collected_at = timestamp(row.get("extracted_at_utc"))
        if collected_at <= scanned:
            before_scan.append(row)
        else:
            after_scan.append(row)
    blank_qq_month = {
        k for k, v in qq.items()
        if not str(v.get("issued_month", "")).strip() and k in extracts
    }
    cross_year_or_blank = {
        k for k in extracts
        if k in qq and k not in qq_year and k not in css_year
    }
    qq_css_gap = qq_year - css_year
    overlap = {k for k in qq_css_gap if k in extracts}
    qq_only = qq_css_gap - overlap

    events = [timestamp(r.get("received_at")) for r in extract_unlinked]
    ingests = [timestamp(r.get("extracted_at_utc")) for r in extract_unlinked]
    all_ingests = [timestamp(r.get("extracted_at_utc")) for r in extracts.values()]
    if any(t > now + dt.timedelta(minutes=5) for t in ingests):
        raise ValueError("EXTRACT_CLOCK_SKEW")

    if age_hours > MAX_AGE_HOURS:
        status = "STALE"
    elif before_scan or blank_qq_month or qq_css_gap:
        status = "HOLD"
    elif after_scan:
        status = "NOT_VERIFIED"  # waiting for next scan, not a proven sink failure
    else:
        status = "PASS"

    result = {
        "status": status,
        "source_scope": YEAR,
        "qq_2026_count": len(qq_year),
        "css_2026_count": len(css_year),
        "extract_count": len(extracts),
        "qq_to_css_gap_count": len(qq_css_gap),
        "qq_gap_in_extract_count": len(overlap),
        "qq_gap_without_extract_count": len(qq_only),
        "extract_not_in_any_qq_or_css_count": len(extract_unlinked),
        "extract_unlinked_before_last_scan": len(before_scan),
        "extract_unlinked_after_last_scan": len(after_scan),
        "qq_blank_month_with_extract": len(blank_qq_month),
        "extract_linked_to_qq_non_2026_scope": len(cross_year_or_blank),
        "source_event_at": max(events).isoformat() if events else None,
        "collected_at": max(ingests).isoformat() if ingests else None,
        "latest_extract_at": max(all_ingests).isoformat() if all_ingests else None,
        "backfill_scan_at": scanned.isoformat(),
        "sink_updated_at": None,  # CSS List has no actual destination update timestamp.
        "verified_at": now.isoformat(),
        "missing_count": len(before_scan),
        "unlinked_count": len(extract_unlinked),
        "original_proof_per_invoice_persisted": False,
        "canonical_owner_approved": False,
        "canonical_writer_enabled": False,
        "business_writes": 0,
        "notes": [
            "An Extract-only invoice collected after the last QQ scan is pending, not SINK_LAG.",
            "Extract rows are not independent original MIME proof or consent to post Revenue.",
            "Blank QQ invoice months and unlinked old Extract rows require provenance review.",
            "Cannot infer sink_updated_at from invoice issued_at or Google Sheet edit time."
        ],
    }
    return result


def main():
    dest = os.environ.get("INVOICE_FRESHNESS_SUMMARY_PATH", "").strip()
    report = {}
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        from qq_invoice_parity_audit import load_rows
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        session = AuthorizedSession(credentials)
        qq = load_rows(session, "QQ 2026 Invoice Backfill", 10000)
        css = load_rows(session, "CSS Tax Invoice List", 2000)
        extracted = load_rows(session, "CSS Tax Invoice Extract", 2000)
        audit = load_rows(session, "QQ Backfill Audit", 100)
        report = summarize(qq, css, extracted, audit)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else ""
        status = ("STALE" if reason == "BACKFILL_SCAN_STALE"
                  else "SOURCE_UNAVAILABLE" if reason.startswith("BACKFILL_") or
                  isinstance(exc, (OSError, KeyError)) or
                  type(exc).__name__ in {"HTTPError", "RefreshError", "TransportError"}
                  else "BLOCK")
        report = {"status": status, "error_type": type(exc).__name__,
                  "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "business_writes": 0}
    # Strictly allowlisted values: summarize() never emits raw IDs or amounts.
    if dest:
        Path(dest).write_text(json.dumps(report, sort_keys=True, ensure_ascii=False)
                              + "\n", encoding="utf-8")
    print("CSS_INVOICE_FRESHNESS " + json.dumps(report, sort_keys=True,
                                               ensure_ascii=False))
    return 0 if report.get("status") in {"PASS", "NO_NEW_DATA"} else 2


if __name__ == "__main__":
    sys.exit(main())
