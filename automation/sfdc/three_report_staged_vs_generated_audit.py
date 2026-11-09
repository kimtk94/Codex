#!/usr/bin/env python3
"""Verify Salesforce report-staging -> derived relationship tabs by independent IDs.

This only proves parity between validated QQ-mail report *staging* and generated
Google Sheet views. It cannot certify current Salesforce records, Save, or CDMS.
No customer rows or identifiers appear in Action output or artifacts.
"""
import base64
from collections import Counter, defaultdict
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.parse

SHEET = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
RANGES = {
    "SFDC Email Leads Raw": "A1:W700",
    "SFDC Email Opportunities Raw": "A1:O1200",
    "SFDC Email Quotation Raw": "A1:Y4500",
    "SFDC Verified Relations": "A1:O1100",
    "SFDC Quote Link Review": "A1:H1100",
    "SFDC Email Ingest Audit": "A1:J10",
    "SFDC Quote Export": "A1:O2000",
}
COLUMNS = {
    "SFDC Email Leads Raw": ("SFDC Lead ID",),
    "SFDC Email Opportunities Raw": ("Opportunity ID", "Opportunity Owner", "Stage"),
    "SFDC Email Quotation Raw": ("SFDC Quotation ID", "Opportunity ID", "Quotation Product ID", "Active"),
    "SFDC Verified Relations": ("Quotation ID", "Opportunity ID", "Quote Process Rows", "Relation State", "Opportunity Owner", "Opportunity Stage", "Quote Active (report only)"),
    "SFDC Quote Link Review": ("Quotation ID", "Quote Process Rows",
        "Distinct Opportunity IDs", "Opportunity ID Missing Rows", "Opportunity IDs Not In Export",
        "Reason", "Review State"),
    "SFDC Quote Export": ("Salesforce Record ID", "AMEA Quotation ID", "Opportunity ID", "Exported At KST", "IsActive"),
    "SFDC Email Ingest Audit": ("Entity", "Source Received KST", "Ingest Checked KST",
        "Rows", "Unique IDs", "Duplicate IDs", "Missing IDs", "Content SHA256", "State"),
}
ALLOWED_STAGING = {"STAGED_NOT_PROMOTED", "PRESERVED_NO_NEW_REPORT"}


def parse(matrix, name):
    min_length = 1 if name in ("SFDC Verified Relations", "SFDC Quote Link Review") else 2
    if not isinstance(matrix, list) or len(matrix) < min_length:
        raise ValueError("SOURCE_OR_SINK_TABLE_EMPTY:" + name)
    header = [str(x).strip() for x in matrix[0]]
    if len(set(header)) != len(header):
        raise ValueError("DUPLICATE_TABLE_HEADER:" + name)
    if any(c not in header for c in COLUMNS[name]):
        raise ValueError("REQUIRED_COLUMN_MISSING:" + name)
    ix = {x: i for i, x in enumerate(header)}
    return [{h: str(row[i]).strip() if i < len(row) and row[i] is not None else ""
             for h, i in ix.items()} for row in matrix[1:] if any(str(v).strip() for v in row)]


def intfield(row, field):
    value = row.get(field, "")
    if not value.isdecimal():
        raise ValueError("MISSING_OR_INVALID_COUNT:" + field)
    return int(value)


def no_duplicates(rows, field, name):
    keys = [r[field] for r in rows]
    if any(not x for x in keys) or len(set(keys)) != len(keys):
        raise ValueError("PRIMARY_ID_MISSING_OR_DUPLICATE:" + name)
    return set(keys)


def audit_source(audit, leads, opportunities, quote_rows):
    source = {r["Entity"]: r for r in audit if r["Entity"] in
              {"Leads", "Opportunities", "Quotation"}}
    if set(source) != {"Leads", "Opportunities", "Quotation"}:
        raise ValueError("SFDCD_REPORT_SOURCE_AUDIT_INCOMPLETE")
    leadids = no_duplicates(leads, "SFDC Lead ID", "Lead")
    oppids = no_duplicates(opportunities, "Opportunity ID", "Opportunity")
    qids = [r["SFDC Quotation ID"] for r in quote_rows]
    if not qids or any(not x for x in qids):
        raise ValueError("QUOTATION_PRIMARY_IDS_INVALID")
    for name, count, unique, duplicates in (
        ("Leads", len(leads), len(leadids), 0),
        ("Opportunities", len(opportunities), len(oppids), 0),
        ("Quotation", len(qids), len(set(qids)), len(qids) - len(set(qids))),
    ):
        row = source[name]
        if (intfield(row, "Rows") != count or intfield(row, "Unique IDs") != unique
            or intfield(row, "Duplicate IDs") != duplicates
            or intfield(row, "Missing IDs") != 0):
            raise ValueError("SFDC_STAGE_AUDIT_COUNT_OR_ID_MISMATCH:" + name)
        if row["State"] not in ALLOWED_STAGING:
            raise ValueError("SFDC_REPORT_STAGE_NOT_ACCEPTED:" + name)
        if not row["Source Received KST"] or not row["Ingest Checked KST"]:
            raise ValueError("SFDC_REPORT_TIMESTAMP_UNAVAILABLE:" + name)
    return {
        "leads": len(leadids), "opportunities": len(oppids),
        "quote_process_rows": len(qids), "unique_quotes": len(set(qids)),
        "quotation_extra_process_rows_not_duplicate_quotes": len(qids) - len(set(qids)),
        "stage_states": {name: source[name]["State"] for name in sorted(source)},
        "source_received_kst": {name: source[name]["Source Received KST"] for name in sorted(source)},
        "ingest_checked_kst": {name: source[name]["Ingest Checked KST"] for name in sorted(source)},
    }


def expected_relation(quote_rows, opportunities):
    """Independent group-level Quote classification: source keys, not names."""
    opp_ids = {r["Opportunity ID"] for r in opportunities}
    grouped = defaultdict(list)
    for r in quote_rows:
        grouped[r["SFDC Quotation ID"]].append(r)
    verified, review, count = {}, {}, Counter()
    for qid, rows in grouped.items():
        known = {r["Opportunity ID"] for r in rows if r["Opportunity ID"]}
        missing = sum(not r["Opportunity ID"] for r in rows)
        outside = len(known - opp_ids)
        reasons = []
        if missing:
            reasons.append("MISSING_OPPORTUNITY_ID")
        if outside:
            reasons.append("OPPORTUNITY_NOT_IN_EXPORT")
        if len(known) != 1:
            reasons.append("MULTIPLE_OR_ZERO_OPPORTUNITY_IDS")
        if reasons:
            review[qid] = {
                "rows": len(rows), "distinct": len(known), "missing": missing,
                "outside": outside, "reason": " | ".join(reasons),
            }
            for reason in reasons:
                count[reason] += 1
        else:
            verified[qid] = {"opportunity": next(iter(known)), "rows": len(rows)}
    return verified, review, dict(sorted(count.items()))


def compare_readback(verified_expected, review_expected, verified_rows, review_rows):
    """Compare generated sink keys and linked values; no writeback."""
    verified_keys = no_duplicates(verified_rows, "Quotation ID", "VerifiedRelation")
    review_keys = no_duplicates(review_rows, "Quotation ID", "QuoteReview")
    if verified_keys & review_keys:
        raise ValueError("SFDC_SINK_VERIFIED_AND_REVIEW_OVERLAP")
    expected_all = set(verified_expected) | set(review_expected)
    actual_all = verified_keys | review_keys
    missing = len(expected_all - actual_all)
    unexpected = len(actual_all - expected_all)
    mismatches = 0
    actual_verified = {r["Quotation ID"]: r for r in verified_rows}
    actual_review = {r["Quotation ID"]: r for r in review_rows}
    for qid, expected in verified_expected.items():
        r = actual_verified.get(qid)
        if (not r or r["Opportunity ID"] != expected["opportunity"]
            or intfield(r, "Quote Process Rows") != expected["rows"]
            or r["Relation State"] != "QUOTE_OPPORTUNITY_ID_VERIFIED_NOT_REVENUE"):
            mismatches += 1
    for qid, expected in review_expected.items():
        r = actual_review.get(qid)
        if (not r or intfield(r, "Quote Process Rows") != expected["rows"]
            or intfield(r, "Distinct Opportunity IDs") != expected["distinct"]
            or intfield(r, "Opportunity ID Missing Rows") != expected["missing"]
            or intfield(r, "Opportunity IDs Not In Export") != expected["outside"]
            or r["Reason"] != expected["reason"] or r["Review State"] != "NEEDS_REVIEW"):
            mismatches += 1
    good = missing == unexpected == mismatches == 0 and verified_keys == set(verified_expected) and review_keys == set(review_expected)
    return {
        "expected_verified_quote_ids": len(verified_expected),
        "expected_review_quote_ids": len(review_expected),
        "sink_verified_quote_ids": len(verified_keys),
        "sink_review_quote_ids": len(review_keys),
        "source_quote_ids_missing_in_sink": missing,
        "sink_quote_ids_not_in_source": unexpected,
        "relation_values_mismatch": mismatches,
        "report_to_generated_readback_status": "PASS_STAGE_TO_GENERATED_ONLY" if good else "SINK_LAG",
        "salesforce_object_save_readback": "NOT_CHECKED",
        "stage_is_live_sfdc_object": False,
    }


def evaluate(tables, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    source = audit_source(tables["SFDC Email Ingest Audit"], tables["SFDC Email Leads Raw"],
        tables["SFDC Email Opportunities Raw"], tables["SFDC Email Quotation Raw"])
    expected, exceptions, reasons = expected_relation(
        tables["SFDC Email Quotation Raw"], tables["SFDC Email Opportunities Raw"])
    sink = compare_readback(expected, exceptions,
        tables["SFDC Verified Relations"], tables["SFDC Quote Link Review"])
    return {
        "verified_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "source_scope": "QQ_SFDC_REPORT_STAGING_ONLY",
        "sink_scope": "GENERATED_GOOGLE_SHEETS_RELATIONS_ONLY",
        "source": source, "relation_exception_reasons": reasons, "sink": sink,
        "sf_object_readback": "SOURCE_UNAVAILABLE",
        "sf_object_id_uniqueness_certified": False,
        "sfdc_save_certified": False,
        "no_finance_or_customer_writes": True,
    }


def session():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("CKD_DRIVE_SA_JSON", "")
    if not raw:
        raise RuntimeError("GOOGLE_SHEETS_AUTH_UNAVAILABLE")
    try:
        info = json.loads(raw)
    except ValueError:
        info = json.loads(base64.b64decode(raw))
    cred = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return AuthorizedSession(cred)


def load_all():
    s = session()
    tables = {}
    for tab, a1 in RANGES.items():
        url = ("https://sheets.googleapis.com/v4/spreadsheets/" + SHEET
               + "/values/" + urllib.parse.quote("'" + tab + "'!" + a1, safe=""))
        response = s.get(url, timeout=65)
        if not response.ok:
            raise RuntimeError("STAGED_OR_GENERATED_SHEET_HTTP_" + str(response.status_code))
        rows = response.json().get("values", [])
        tables[tab] = parse(rows, tab)
    return tables


def main():
    from three_report_owner_scope import owner_report_audit
    tables = load_all()
    report = evaluate(tables)
    owner = owner_report_audit(tables)
    from three_report_owner_historical_quote_evidence import compare_owner_priority
    history = compare_owner_priority(
        tables["SFDC Email Opportunities Raw"], tables["SFDC Email Quotation Raw"],
        tables["SFDC Quote Export"],
    )
    if history["owner_without_staged_quote_opportunities"] != owner["owner_opportunities_without_verified_quotes"]:
        raise ValueError("OWNER_123_UNLINKED_SCOPE_DISAGREES_WITH_HISTORICAL_TRIAGE")
    report["owner_scope"] = owner
    report["owner_historical_quote_corrob"] = history
    folder = Path("audit-results")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "css-sfdc-report-generated-parity.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    compact = {
        "source": {k: v for k, v in report["source"].items() if k not in
                   ("source_received_kst", "ingest_checked_kst")},
        "exception_reasons": report["relation_exception_reasons"],
        "sink": report["sink"],
        "owner_scope": owner,
        "owner_historical_quote_corrob": history,
        "sfdc_object_readback": "SOURCE_UNAVAILABLE",
        "source_original_qq_attachment_compared": False,
        "financial_mutations": 0,
    }
    print("CSS_SFDC_STAGED_GENERATED_PARITY=" + json.dumps(compact, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## SFDC staged report -> generated view parity (read-only)\n\n")
            f.write("Source stage rows: " + str(report["source"]["quote_process_rows"]) +
                    "; unique quote IDs: " + str(report["source"]["unique_quotes"]) + "\n\n")
            f.write("Verified relations: " + str(report["sink"]["sink_verified_quote_ids"]) +
                    "; review-only relations: " + str(report["sink"]["sink_review_quote_ids"]) +
                    "; result: **" + report["sink"]["report_to_generated_readback_status"] + "**\n\n")
            f.write("Owner exact opportunity IDs: " + str(owner["owner_opportunities"]) +
                    "; owner verified Quote IDs: " + str(owner["owner_verified_quote_ids"]) +
                    "; unattributable review Quote IDs: " + str(owner["review_unattributable_quote_ids"]) +
                    "; source owner/stage/active readback: **" + owner["scope_status"] + "**\\n\\n")
            f.write("Owner stage-priority opportunity review: " +
                    str(history["priority_opportunity_count"]) +
                    "; corroborated in older Quote Export: " +
                    str(history["priority_with_historic_record_id"]) +
                    "; old export absent: " +
                    str(history["priority_without_historic_record_id"]) +
                    "; review: **" + history["review_status"] + "**\\n\\n")
            f.write("Original Salesforce object Save/readback: **NOT CHECKED**. "
                    "Report staging is not a live SFDC object query.\n")
    if history["review_status"] not in (
        "PASS_HISTORICAL_CORROBORATION_ONLY",
        "REVIEW_HISTORICAL_EXPORT_OPPORTUNITY_ID_GAP",
    ):
        print("CSS_SFDC_HISTORICAL_QUOTE_EVIDENCE_BLOCKED", file=sys.stderr)
        return 2
    if owner["scope_status"] != "PASS_REPORT_OWNER_TO_SINK_ONLY":
        print("CSS_SFDC_OWNER_SCOPE_READBACK_BLOCKED", file=sys.stderr)
        return 2
    if report["sink"]["report_to_generated_readback_status"] != "PASS_STAGE_TO_GENERATED_ONLY":
        print("CSS_SFDC_GENERATED_READBACK_BLOCKED", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("CSS_SFDC_STAGED_PARITY_ERROR=" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
