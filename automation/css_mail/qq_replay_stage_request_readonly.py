#!/usr/bin/env python3
"""Owner-private seven-invoice Stage-only REQUEST review; no write authority.

The request tab is a HUMAN INTENT inventory, not an approval signature.
No HTTP, mail, Sheets writes, JWT, filesystem receipts or unlock API.
All public outputs are aggregates; never print invoice IDs, UIDs or names.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re

REQUEST_TAB = "건별 Stage 승인 요청 (미실행)"
REQUEST_HEADER = (
    "No.", "Invoice Number", "Amount KRW", "IMAP UID", "UIDVALIDITY",
    "Original PDF Filename", "Scope", "Review Status",
    "Execution Request", "Confirmation Phrase", "Requested By",
    "Requested At UTC", "Authorization Status", "Request Notes",
)
ALLOWED = ("NOT_REQUESTED", "REQUEST_STAGE_ONLY", "REJECT")
CONFIRMATION = "QQ_STAGE_ONLY"


def txt(v):
    return str(v if v is not None else "").strip()


def posint(v):
    value = txt(v)
    return int(value) if re.fullmatch(r"[0-9]+",value) and int(value) > 0 else None


def stamp(v):
    try:
        result = datetime.fromisoformat(txt(v).replace("Z","+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def assess_requests(rows, review, plan, now):
    """Validate exactly 7 intent rows and never grant real execution.

    A user-controllable Google Sheets value, even coupled with a name and
    timestamp, is not independently authenticated financial authorization.
    Actual stage-only dispatch, protected environment review, writer
    exclusion, durable receipts and post-write readback are not implemented.
    """
    if (not isinstance(now,datetime) or now.tzinfo is None
            or len(rows)!=7 or len(review)!=7 or len(plan)!=7):
        raise ValueError("REQUEST_SCOPE_INVALID")
    invoices=[txt(x.get("Invoice Number")) for x in rows]
    if len(set(invoices))!=7 or any(not re.fullmatch(r"[0-9]{10,15}",k) for k in invoices):
        raise ValueError("REQUEST_DUPLICATE_OR_INVALID_INVOICE")
    rm={txt(x.get("Invoice Number")):x for x in review}
    pm={txt(x.get("invoice_number")):x for x in plan}
    if len(rm)!=7 or len(pm)!=7 or set(rm)!=set(invoices) or set(pm)!=set(invoices):
        raise ValueError("REQUEST_PLAN_OR_REVIEW_SCOPE_INVALID")
    counts=Counter()
    now=now.astimezone(timezone.utc)
    for i,row in enumerate(rows,1):
        key=invoices[i-1]
        r=rm[key]
        p=pm[key]
        if (txt(row.get("No."))!=str(i)
                or txt(row.get("Invoice Number"))!=txt(p.get("invoice_number"))
                or posint(row.get("Amount KRW"))!=posint(p.get("amount_krw"))
                or txt(row.get("IMAP UID"))!=txt(p.get("imap_uid"))
                or txt(row.get("UIDVALIDITY"))!=txt(r.get("UIDVALIDITY"))
                or txt(row.get("Original PDF Filename"))!=txt(p.get("filename"))
                or txt(row.get("Scope"))!="QQ_STAGE_ONLY"
                or txt(row.get("Review Status"))!=txt(r.get("Review Selection (NOT WRITE APPROVAL)"))
                or txt(row.get("Authorization Status"))!="NOT_AUTHORIZED"):
            counts["binding_conflict"]+=1
            continue
        selection=txt(row.get("Execution Request"))
        if selection not in ALLOWED:
            counts["invalid_selection"]+=1
            continue
        confirmation=txt(row.get("Confirmation Phrase"))
        requested_by=txt(row.get("Requested By"))
        at=txt(row.get("Requested At UTC"))
        if selection=="NOT_REQUESTED":
            if confirmation or requested_by or at:
                counts["unexpected_request_metadata"]+=1
            else:
                counts["not_requested"]+=1
            continue
        if selection=="REJECT":
            # A rejection is always non-authoritative and never a request.
            counts["rejected"]+=1
            continue
        # A completed request is NEVER an authenticated approval.
        if txt(r.get("Review Selection (NOT WRITE APPROVAL)"))!="REVIEW_OK":
            counts["review_not_confirmed"]+=1
        elif confirmation != CONFIRMATION or not requested_by or len(requested_by)>120:
            counts["confirmation_missing"]+=1
        elif not stamp(at) or stamp(at)>now or now-stamp(at)>timedelta(hours=24):
            counts["request_expired_or_invalid"]+=1
        else:
            counts["request_ready_for_separate_review"]+=1
    return {
        "request_status":"HOLD",
        "request_case_count":7,
        "request_not_requested_count":counts["not_requested"],
        "request_rejected_count":counts["rejected"],
        "request_binding_conflict_count":counts["binding_conflict"],
        "request_invalid_selection_count":counts["invalid_selection"],
        "request_unexpected_metadata_count":counts["unexpected_request_metadata"],
        "request_review_not_confirmed_count":counts["review_not_confirmed"],
        "request_confirmation_missing_count":counts["confirmation_missing"],
        "request_expired_or_invalid_count":counts["request_expired_or_invalid"],
        "request_ready_for_separate_review_count":
            counts["request_ready_for_separate_review"],
        "request_authenticated_approvals":0,
        "request_single_writer_lock_verified":0,
        "request_stage_writes":0,
        "request_cursor_writes":0,
        "request_canonical_writes":0,
        "request_is_execution_approval":False,
    }
