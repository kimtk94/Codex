#!/usr/bin/env python3
"""Private QQ seven-row recovery plan comparison, strictly READ ONLY."""
from collections import Counter
import re

PLAN_HEADER = (
    "invoice_number", "issued_month", "amount_krw", "amea_project_id",
    "h_project_id", "po_reference", "imap_folder", "imap_uid", "filename",
    "evidence", "backfill_utc",
)

def txt(value):
    return str(value if value is not None else "").strip()

def amount(value):
    raw=txt(value)
    return int(raw) if re.fullmatch(r"[0-9]+",raw) and int(raw)>0 else None

def validate_plan(plan, review, extracts, stage, canonical):
    """Compare plan to original Extract and live sinks; never grants approval."""
    if not isinstance(plan,list) or len(plan)!=7:
        raise ValueError("PLAN_SEVEN_ROWS_REQUIRED")
    ids=[txt(row.get("invoice_number")) for row in plan]
    if len(set(ids))!=7 or any(not re.fullmatch(r"[0-9]{10,15}",x) for x in ids):
        raise ValueError("PLAN_DUPLICATE_OR_INVALID_INVOICE")
    reviews={txt(x.get("Invoice Number")):x for x in review}
    if len(reviews)!=7 or set(reviews)!=set(ids):
        raise ValueError("PLAN_REVIEW_SCOPE_CHANGED")
    src={}
    for r in extracts:
        key=txt(r.get("invoice_number"))
        if key in src:
            raise ValueError("PLAN_SOURCE_DUPLICATE")
        if key:
            src[key]=r
    stage_ids=[txt(r.get("invoice_number")) for r in stage+canonical]
    if len([x for x in stage_ids if x])!=len(set(x for x in stage_ids if x)):
        raise ValueError("PLAN_SINK_DUPLICATE")
    current=set(stage_ids)
    reasons=Counter()
    for row in plan:
        key=txt(row["invoice_number"])
        e=src.get(key)
        r=reviews[key]
        if key in current:
            reasons["existing_sink"]+=1
            continue
        if e is None or txt(e.get("validation_status"))!="FILENAME_PARSED":
            reasons["source_missing"]+=1
            continue
        expected={
            "invoice_number":key, "issued_month":"",
            "amount_krw":amount(e.get("amount_krw")),
            "amea_project_id":txt(e.get("project_id")),
            "h_project_id":txt(e.get("h_project_number")),
            "po_reference":txt(e.get("po_reference")),
            "imap_folder":"INBOX", "imap_uid":txt(e.get("imap_uid")),
            "filename":txt(e.get("attachment_filename")),
            "evidence":txt(e.get("validation_status")), "backfill_utc":"",
        }
        if not expected["amount_krw"] or not expected["imap_uid"].isdigit() or not expected["filename"]:
            reasons["incomplete_source"]+=1
            continue
        if (txt(r.get("Current Status"))!="HOLD"
            or amount(r.get("Amount KRW"))!=expected["amount_krw"]
            or txt(r.get("IMAP UID"))!=expected["imap_uid"]
            or txt(r.get("Original PDF Filename"))!=expected["filename"]):
            reasons["review_mismatch"]+=1
            continue
        if txt(row.get("issued_month")) or txt(row.get("backfill_utc")):
            reasons["invented_month_or_timestamp"]+=1
            continue
        if amount(row.get("amount_krw"))!=expected["amount_krw"]:
            reasons["amount_mismatch"]+=1
            continue
        nonnumeric=[k for k in PLAN_HEADER if k not in
                    ("issued_month","amount_krw","backfill_utc")]
        if any(txt(row.get(k))!=expected[k] for k in nonnumeric):
            reasons["identity_mismatch"]+=1
            continue
        reasons["matched"]+=1
    if sum(reasons.values())!=7:
        raise ValueError("PLAN_COVERAGE_INCOMPLETE")
    output={
        "plan_status":"HOLD", "plan_cases":7,
        "plan_source_match_count":reasons["matched"],
        "plan_existing_sink_count":reasons["existing_sink"],
        "plan_missing_source_count":reasons["source_missing"],
        "plan_incomplete_source_count":reasons["incomplete_source"],
        "plan_review_mismatch_count":reasons["review_mismatch"],
        "plan_invented_month_or_time_count":reasons["invented_month_or_timestamp"],
        "plan_amount_mismatch_count":reasons["amount_mismatch"],
        "plan_identity_mismatch_count":reasons["identity_mismatch"],
        "plan_authenticated_approvals":0, "plan_actual_stage_writes":0,
        "plan_cursor_writes":0, "plan_canonical_writes":0,
        "plan_writer_exclusion_verified":0,
    }
    return output
