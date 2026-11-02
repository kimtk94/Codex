#!/usr/bin/env python3
"""Verify Salesforce Opportunity -> Related Quotation -> live report -> business Opp-ID.

The report must be filtered on one exact QID, and all visible report product rows
must be accounted for. Never rely on report names, unsynced Sheet exports, or an
Opportunity name string. Does NOT enable Salesforce Save.
"""
import argparse
import json
import re
from pathlib import Path

from related_quotation_bridge import (
    BUSINESS, QID, QUOTE_RECORD, SF_RECORD, same_record,
)

REPORT_ID = re.compile(r"00O[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")


def verify(evidence, report):
    """Pure fail-closed verifier. Input JSON is local sensitive UI evidence."""
    parent = str(evidence.get("opportunity_record_id") or "")
    related_quote = str(evidence.get("related_quote_record_id") or "")
    detail_quote = str(evidence.get("quotation_record_id") or "")
    qid = str(evidence.get("related_qid") or "")
    if (evidence.get("source") != "Salesforce Opportunity Related + Quotation visible UI"
            or evidence.get("salesforce_modified") is not False
            or not SF_RECORD.fullmatch(parent)
            or not QUOTE_RECORD.fullmatch(related_quote)
            or not QUOTE_RECORD.fullmatch(detail_quote)
            or not same_record(related_quote, detail_quote)
            or not QID.fullmatch(qid)):
        raise ValueError("Authoritative, read-only Opportunity-to-Quote evidence required")
    if (report.get("source") != "Salesforce Report Viewer UI"
            or report.get("salesforce_modified") is not False
            or not REPORT_ID.fullmatch(str(report.get("report_id") or ""))
            or report.get("exact_qid_filter") != qid
            or report.get("filter_operator") != "equals"):
        raise ValueError("Live Salesforce report with exact-QID filter required")
    rows = report.get("rows")
    total = report.get("total_records")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise ValueError("Actual displayed report rows and Total Records required")
    if total <= 0 or total > 2000 or len(rows) != total:
        return _result("REPORT_ROWS_INCOMPLETE_OR_EMPTY", parent, detail_quote, qid)
    all_ids = []
    for row in rows:
        if not isinstance(row, dict):
            return _result("REPORT_ROW_INVALID", parent, detail_quote, qid)
        if row.get("qid") != qid or not same_record(row.get("quotation_record_id"), detail_quote):
            return _result("REPORT_ROW_QUOTE_ID_CONFLICT", parent, detail_quote, qid)
        business_id = str(row.get("business_opportunity_id") or "").strip()
        if not BUSINESS.fullmatch(business_id):
            return _result("REPORT_ROW_BUSINESS_ID_INVALID", parent, detail_quote, qid)
        all_ids.append(business_id)
    if len(set(all_ids)) != 1:
        return _result("CONFLICTING_BUSINESS_IDS", parent, detail_quote, qid)
    return _result("VERIFIED_BY_LIVE_QUOTATION_REPORT", parent, detail_quote,
                   qid, all_ids[0], total)


def _result(status, parent, quote, qid, business_id=None, rows=0):
    verified = status == "VERIFIED_BY_LIVE_QUOTATION_REPORT"
    return {
        "version": "live-related-quote-report-bridge-v1",
        "status": status,
        "source": "read-only Salesforce UI cross-record proof",
        "opportunity_record_id": parent,
        "quotation_record_id": quote,
        "related_qid": qid,
        "business_opportunity_id": business_id if verified else None,
        "verified_product_rows": rows if verified else 0,
        "identity_verified": verified,
        "review_required": True,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--related-evidence", required=True)
    p.add_argument("--report-evidence", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    related = json.loads(Path(a.related_evidence).read_text(encoding="utf-8-sig"))
    report = json.loads(Path(a.report_evidence).read_text(encoding="utf-8-sig"))
    result = verify(related, report)
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE ID BRIDGE:", result["status"])
    print("VERIFIED PRODUCT ROW COUNT:", result["verified_product_rows"])
    print("REVIEW REQUIRED:", result["review_required"])
    print("SALESFORCE SAVE ALLOWED:", result["save_allowed"])
    print("PRIVATE OUTPUT:", target)


if __name__ == "__main__":
    main()
