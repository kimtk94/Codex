#!/usr/bin/env python3
"""Read-only evidence of canonical revenue Sheet mirror consistency and snapshot age.

Unlike a live QQ Tax Invoice / Feishu Base readback, this probes THREE tabs of
one Google Sheet. It must never certify actual invoice issuance, latest QQ mail,
cash payment, Feishu Base propagation, or source-to-sink parity.

No customer-level data, invoice amounts, credentials, or private row identifiers
are written to stdout or the CI artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation" / "feishu"))
from monthly_revenue_canonical import evidence_rows, RevenueEvidenceError

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TABS = {
    "BI Revenue Net VAT Monthly": 120,
    "BI Revenue Lifecycle Monthly": 120,
    "Revenue Source Authority": 250,
}
KST = ZoneInfo("Asia/Seoul")
SOURCE_CLAIM = "GOOGLE_SHEETS_MIRROR_ONLY"
MAX_SNAPSHOT_AGE_HOURS = 48.0  # Review threshold, NOT a verified upstream cadence.


def now_kst():
    return dt.datetime.now(KST)


def parse_kst(text):
    if not isinstance(text, str):
        raise ValueError("MIRROR_TIMESTAMP_MISSING")
    parsed = dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S KST")
    return parsed.replace(tzinfo=KST)


def rows_to_dict(values):
    if not isinstance(values, list) or len(values) < 2:
        raise ValueError("MIRROR_SHEET_EMPTY")
    header = [str(cell).strip() for cell in values[0]]
    if not header or any(not x for x in header) or len(header) != len(set(header)):
        raise ValueError("MIRROR_HEADERS_INVALID")
    rows = []
    for values_row in values[1:]:
        if values_row and any(str(cell).strip() for cell in values_row):
            if len(values_row) > len(header):
                raise ValueError("MIRROR_UNEXPECTED_COLUMNS")
            rows.append({column: str(values_row[i]).strip() if i < len(values_row) else ""
                         for i, column in enumerate(header)})
    if not rows:
        raise ValueError("MIRROR_NO_RECORDS")
    return rows


def measure(source, *, month, checked_at=None, max_age_hours=MAX_SNAPSHOT_AGE_HOURS):
    """Compute a minimal sanitized receipt; never return raw source values."""
    checked_at = checked_at or now_kst()
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("CHECKED_AT_TIMEZONE_REQUIRED")
    if type(max_age_hours) not in (int, float) or not 0 < max_age_hours <= 720:
        raise ValueError("SNAPSHOT_AGE_THRESHOLD_INVALID")
    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
        raise ValueError("MONTH_INVALID")
    # Fail closed through the same canonical reconciliation contract used by
    # the existing monthly revenue writer, without executing that writer.
    reconciled = evidence_rows(source)
    selected = [r for r in reconciled if r["Month"] == month]
    if len(selected) != 1:
        raise ValueError("TARGET_MONTH_NOT_CERTIFIED_BY_MIRROR")
    net = next((r for r in source["BI Revenue Net VAT Monthly"] if r.get("Month") == month), None)
    lifecycle = next((r for r in source["BI Revenue Lifecycle Monthly"] if r.get("Month") == month), None)
    authority = [r for r in source["Revenue Source Authority"]
                 if r.get("Month") == month and
                 r.get("Source Role") in ("CANONICAL_ACTUAL_GROSS", "CANONICAL_ISSUED_NET")]
    if net is None or lifecycle is None or len(authority) != 2:
        raise ValueError("MIRROR_REVIEW_TIMESTAMP_MISSING")
    timestamps = [
        parse_kst(net.get("Verified At KST")),
        parse_kst(lifecycle.get("Snapshot KST")),
        *(parse_kst(x.get("Verified KST")) for x in authority),
    ]
    age_hours = [(checked_at - at).total_seconds() / 3600 for at in timestamps]
    if any(age < -0.1 for age in age_hours):
        raise ValueError("MIRROR_FUTURE_VERIFICATION_TIMESTAMP")
    oldest_age = max(age_hours)
    aged = oldest_age > max_age_hours
    return {
        "schema_version": 1,
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "month": month,
        "source_scope": SOURCE_CLAIM,
        "source_tabs_checked": 3,
        "canonical_reconciled_months": len(reconciled),
        "three_way_aggregate_parity": True,
        "snapshot_review_age_threshold_hours": max_age_hours,
        "snapshot_age_state": "AGED_RECHECK" if aged else "WITHIN_REVIEW_THRESHOLD",
        "status": "MIRROR_3WAY_PARITY_AGED" if aged else "MIRROR_3WAY_PARITY_RECENT",
        "business_source_original_probed": False,
        "feishu_base_sink_readback_probed": False,
        "original_tax_invoice_mail_verified": False,
        "payment_receipt_verified": False,
        "business_source_sink_verification": "NOT_VERIFIED",
        "no_business_writes": True,
    }


def mirror_source():
    # Missing credentials must be classified before importing optional Google
    # clients, so offline PR tests work without network/package setup.
    raw = os.getenv("CKD_DRIVE_SA_JSON", "").strip()
    if not raw:
        raise RuntimeError("MIRROR_READ_CREDENTIALS_UNAVAILABLE")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(credentials)
    result = {}
    for title, max_rows in TABS.items():
        a1 = "'" + title.replace("'", "''") + "'!A1:AZ" + str(max_rows)
        url = ("https://sheets.googleapis.com/v4/spreadsheets/" + BOOK
               + "/values/" + urllib.parse.quote(a1, safe=""))
        response = session.get(url, timeout=45)
        response.raise_for_status()
        result[title] = rows_to_dict(response.json().get("values"))
    return result


def write_receipt(report, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## Autonomous Next — Monthly Revenue mirror evidence",
        f"- Status: **{report['status']}**",
        f"- Snapshot review age: **{report.get('snapshot_age_state', 'NOT_CHECKED')}**",
        f"- Aggregate source sheets checked: **{report.get('source_tabs_checked', 0)}/3**",
        "- Authenticated QQ original source: **NOT VERIFIED**",
        "- Feishu Base destination readback: **NOT VERIFIED**",
        "- No monetary amounts, customer rows, invoice identifiers or business writes emitted.",
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=now_kst().strftime("%Y-%m"))
    ap.add_argument("--out", type=Path, default=Path("autonomous-next-triage/monthly-revenue-mirror.json"))
    args = ap.parse_args()
    try:
        result = measure(mirror_source(), month=args.month)
        write_receipt(result, args.out)
        # An aged but internally consistent snapshot is an investigation
        # candidate; not a live-source failure. Preserve the full artifact.
        return 0
    except (ValueError, RevenueEvidenceError, RuntimeError, OSError, KeyError, TypeError) as exc:
        # Intentionally never print str(exc): source and library exception text
        # may contain private data. Category is enough for the public CI summary.
        result = {
            "schema_version": 1,
            "checked_at": now_kst().isoformat(timespec="seconds"),
            "month": args.month,
            "source_scope": SOURCE_CLAIM,
            "status": "MIRROR_UNAVAILABLE_OR_MISMATCH",
            "error_category": type(exc).__name__,
            "business_source_sink_verification": "NOT_VERIFIED",
            "business_source_original_probed": False,
            "feishu_base_sink_readback_probed": False,
            "no_business_writes": True,
        }
        write_receipt(result, args.out)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
