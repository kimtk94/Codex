#!/usr/bin/env python3
"""Read-only bridge for Salesforce Opportunity -> Related Quotation__c -> Quote Export.

The Quote Export column "AMEA Quotation ID" currently contains QID-* values,
NOT the AMEA project number. Never confuse the two. No Save or Salesforce API.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SF_RECORD = re.compile(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
QUOTE_RECORD = re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
QID = re.compile(r"QID-\d{4}-\d{2}-\d{2}-\d+\Z")
BUSINESS = re.compile(r"Opp-\d{4}-\d{2}-\d{2}-\d+\Z")


def same_record(a, b):
    a, b = str(a or "").strip(), str(b or "").strip()
    if len(a) not in (15, 18) or len(b) not in (15, 18):
        return False
    # First 15 characters of a Salesforce ID are case-sensitive.
    return a[:15] == b[:15]


def age_hours(value, at_time):
    """Known KST export timestamps only; fail closed on missing or malformed values."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) KST", str(value or ""))
    if not match:
        return None
    try:
        from datetime import timedelta
        stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone(timedelta(hours=9)))
        delta = (at_time - stamp).total_seconds() / 3600
        return delta if delta >= 0 else None
    except ValueError:
        return None


def bridge(evidence, rows, at_time=None, max_source_age_hours=72):
    """Return statuses rather than guessing through names or the wrong object IDs."""
    at_time = at_time or datetime.now(timezone.utc)
    if not isinstance(rows, list):
        raise ValueError("Quote Export rows must be a list")
    parent = str(evidence.get("opportunity_record_id") or "")
    from_related = str(evidence.get("related_quote_record_id") or "")
    detail = str(evidence.get("quotation_record_id") or "")
    qid = str(evidence.get("related_qid") or "")
    if (evidence.get("source") != "Salesforce Opportunity Related + Quotation visible UI"
            or evidence.get("salesforce_modified") is not False
            or not SF_RECORD.fullmatch(parent)
            or not QUOTE_RECORD.fullmatch(from_related)
            or not QUOTE_RECORD.fullmatch(detail)
            or not same_record(from_related, detail)
            or not QID.fullmatch(qid)):
        raise ValueError("Exact, read-only Opportunity-to-Quotation route evidence required")
    matches_id = [r for r in rows if isinstance(r, dict)
                  and same_record(r.get("Salesforce Record ID"), detail)]
    matches_qid = [r for r in rows if isinstance(r, dict)
                   and str(r.get("AMEA Quotation ID") or "").strip() == qid]
    both = [r for r in matches_id if str(r.get("AMEA Quotation ID") or "").strip() == qid]
    candidate = both[0] if len(both) == 1 else None
    valid_business = candidate and BUSINESS.fullmatch(str(candidate.get("Opportunity ID") or "").strip())
    age = age_hours(candidate.get("Exported At KST"), at_time) if candidate else None
    if len(matches_id) > 1 or len(matches_qid) > 1 or len(both) > 1:
        status = "AMBIGUOUS_SOURCE_RECORD"
    elif not both and (matches_id or matches_qid):
        status = "QUOTE_RECORD_QID_CONFLICT"
    elif not both:
        status = "QUOTE_NOT_IN_SOURCE"
    elif not valid_business:
        status = "BUSINESS_ID_MISSING_OR_INVALID"
    elif age is None or age > max_source_age_hours:
        status = "SOURCE_EXPORT_STALE_OR_UNVERIFIED"
    else:
        status = "SOURCE_BACKED_RELATED_QUOTE_MATCH"
    # The bridge maps IDs for a human-reviewed, unsaved draft. It never grants Save.
    verified = status == "SOURCE_BACKED_RELATED_QUOTE_MATCH"
    return {
        "version": "related-quotation-bridge-v1",
        "status": status,
        "source_quote_row_count": len(both),
        "source_record_key_count": len(matches_id),
        "source_qid_key_count": len(matches_qid),
        "source_freshness_hours": round(age, 2) if age is not None else None,
        "opportunity_business_id": str(candidate["Opportunity ID"]) if verified else None,
        "reference_reuse_allowed": verified,
        "save_allowed": False,
        "salesforce_save_performed": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--private-ui-evidence", required=True,
                   help="Private redacted-compatible local metadata JSON, never commit")
    p.add_argument("--source-export-json", required=True,
                   help="Current SFDC Quote Export JSON rows (column names preserved)")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    evidence = json.loads(Path(a.private_ui_evidence).read_text(encoding="utf-8-sig"))
    raw = json.loads(Path(a.source_export_json).read_text(encoding="utf-8-sig"))
    rows = raw if isinstance(raw, list) else raw.get("rows", [])
    result = bridge(evidence, rows)
    path = Path(a.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Do not print any exact CRM/Quote/QID/AMEA/customer identifiers.
    print("SOURCE LINK STATUS:", result["status"])
    print("RELATED QUOTE SOURCE ROW COUNT:", result["source_quote_row_count"])
    print("REUSE ALLOWED:", result["reference_reuse_allowed"])
    print("SAVE ALLOWED:", result["save_allowed"])
    print("PRIVATE OUTPUT:", path)


if __name__ == "__main__":
    main()
