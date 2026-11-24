#!/usr/bin/env python3
"""Publicly safe status of a captured, *readonly* QQ Backfill preview.

Never prints subprocess stderr/stdout: these may include invoice identifiers,
private IMAP folders, API response bodies, credentials or customer data.
"""
import json
import re

STAGES = (
    "START",
    "SHEETS_AUTH_READY",
    "SHEETS_METADATA_LOADED",
    "STAGING_SOURCE_LOADED",
    "CURSOR_AUDIT_LOADED",
    "LEGACY_SEED_RECONCILED",
    "IMAP_AUTHENTICATED",
    "IMAP_MAILBOXES_LISTED",
    "SOURCE_SCAN_FINISHED",
)

ERROR_CODES = (
    "BACKFILL_WRITE_MODE_INVALID",
    "BACKFILL_WRITER_APPROVAL_GATE",
    "BACKFILL_PREVIEW_SOURCE_TAB_MISSING",
    "BACKFILL_PREVIEW_AUDIT_TAB_MISSING",
    "BACKFILL_HEADER_MISMATCH",
    "CURSOR_SCHEMA_MISMATCH",
    "AUDIT_SCHEMA_MISMATCH",
    "VERIFIED_SEED_AMOUNT_CONFLICT",
    "IMAP_LIST_FAILED",
    "UIDVALIDITY_UNAVAILABLE_AFTER_STATUS",
    "QQ_BACKFILL_SEARCH_UNAVAILABLE",
    "QQ_BACKFILL_NO_INVOICE_EVIDENCE_CHECK_SUBJECT_SEARCH_OR_BODYSTRUCTURE",
    "BACKFILL_ROWS_EXCEED_LIMIT",
)
REASONS = (
    "KNOWN_UID_WITH_VALID_EVIDENCE",
    "ORIGINAL_ISSUED_PROOF_PERSISTED",
    "ORIGINAL_NONOFFICIAL_HEADER_VERIFIED",
    "FETCH_FAILED",
    "ORIGINAL_HEADER_UNAVAILABLE",
    "MIME_PARSER_UNRESOLVED",
    "AMOUNT_CONFLICT",
    "ARRIVAL_VALID_ARRIVAL_DATE",
    "ARRIVAL_UNSUPPORTED_FORMAT",
    "ARRIVAL_TOKEN_ABSENT",
    "ARRIVAL_FETCH_ERROR",
)
BLOCK_CAUSE_FIELDS = (
    "UIDVALIDITY_MISSING_WITH_CANDIDATES",
    "UIDVALIDITY_ROLE_INBOX",
    "UIDVALIDITY_ROLE_OTHER",
    "UIDVALIDITY_STATUS_OK",
    "UIDVALIDITY_STATUS_NO",
    "UIDVALIDITY_STATUS_BAD",
    "UIDVALIDITY_STATUS_OTHER",
    "UIDVALIDITY_SELECTED_RESPONSE_EMPTY",
    "UIDVALIDITY_SELECTED_RESPONSE_NONEMPTY",
    "UIDVALIDITY_STATUS_RESPONSE_EMPTY",
    "UIDVALIDITY_STATUS_RESPONSE_NONEMPTY",
    "SCAN_LIMIT_AT_FOLDER_START",
    "SCAN_LIMIT_INCOMPLETE",
    "UNRESOLVED_SOURCE_UID",
    "CONSERVATIVE_CHECKPOINT_BLOCKED",
    "FOLDER_SELECT_SKIPPED",
)
COUNT_FIELDS = (
    "scanned",
    "new_in_memory",
    "would_update_cursor_folders",
    "blocked",
    "sheet_writes",
    "cursor_writes",
)
ERR_TYPES = (
    "RuntimeError", "ValueError", "KeyError", "TypeError", "IndexError",
    "AttributeError", "ConnectionError", "TimeoutError", "SSLError",
    "RefreshError", "HTTPError", "IMAP4.error", "UnicodeDecodeError",
    "JSONDecodeError",
)


def classify_preview(returncode, stdout, stderr):
    """Return allowlisted statuses/counts only, without copying source lines."""
    out = str(stdout or "")
    err = str(stderr or "")
    seen = [
        line.split("QQ_SAFE_STAGE=", 1)[1].strip()
        for line in out.splitlines()
        if line.startswith("QQ_SAFE_STAGE=")
        and line.split("QQ_SAFE_STAGE=", 1)[1].strip() in STAGES
    ]
    stage = seen[-1] if seen else "NO_STAGE_MARKER"
    report = {
        "status": "HOLD",
        "last_completed_stage": stage,
        "exception_code": "UNCLASSIFIED",
        "exception_type": "UNKNOWN",
        "preview_returncode_class": (
            "EXPECTED_NOT_COMMITTED" if returncode == 2 else
            "ZERO_UNEXPECTED" if returncode == 0 else
            "OTHER_NONZERO"),
        "business_writes": 0,
    }
    for code in ERROR_CODES:
        # Whole-token guard prevents printing a custom/user-generated message.
        if re.search(r"(?<![A-Za-z0-9_])"+re.escape(code)+r"(?![A-Za-z0-9_])", err):
            report["exception_code"] = code
            break
    if report["exception_code"] == "UNCLASSIFIED":
        if re.search(r"\bSHEETS_(?:400|401|403|404|429|500|502|503)\b", err):
            report["exception_code"] = "SHEETS_HTTP_ERROR"
        elif re.search(r"\b(?:LOGIN failed|authentication failed)\b", err, re.I):
            report["exception_code"] = "IMAP_AUTH_FAILED"
    for kind in ERR_TYPES:
        if re.search(r"(?:^|\n)(?:[A-Za-z_.]+\.)?"+re.escape(kind)+r"(?::|\s*$)", err):
            report["exception_type"] = kind
            break
    prefix = "QQ_BACKFILL_PARSER_DIAGNOSTIC "
    for line in out.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            data = json.loads(line[len(prefix):].split(" fallback_verified=", 1)[0])
            if isinstance(data, dict):
                report["reason_counts"] = {
                    k: int(data[k]) for k in REASONS
                    if k in data and type(data[k]) is int and data[k] >= 0
                }
        except (ValueError, TypeError):
            pass
        break
    block_reports = [line for line in out.splitlines()
                     if line.startswith("QQ_BACKFILL_BLOCK_DIAGNOSTIC ")]
    if len(block_reports) == 1:
        try:
            raw = json.loads(block_reports[0].split(" ", 1)[1])
            if isinstance(raw, dict):
                report["block_reason_counts"] = {
                    k: raw[k] for k in BLOCK_CAUSE_FIELDS
                    if k in raw and type(raw[k]) is int and 0 <= raw[k] <= 1000000
                }
        except (ValueError, TypeError):
            pass
    safe_search_lines = [line for line in out.splitlines()
                         if line.startswith("QQ_SAFE_SEARCH_FAILURE ")]
    if len(safe_search_lines) == 1:
        try:
            raw = json.loads(safe_search_lines[0].split(" ", 1)[1])
            valid = (
                isinstance(raw, dict) and
                raw.get("folder_role") in ("INBOX", "OTHER") and
                type(raw.get("folder_ordinal")) is int and
                1 <= raw["folder_ordinal"] <= 10000 and
                raw.get("criterion") in ("ISSUED", "TAX") and
                raw.get("status_class") in ("OK", "NO", "BAD", "OTHER") and
                raw.get("row_class") in ("BYTES", "NON_SEQUENCE",
                                        "EMPTY_SEQUENCE", "FIRST_NOT_BYTES")
            )
            if valid:
                report["search_failure"] = {
                    k: raw[k] for k in (
                        "folder_role", "folder_ordinal", "criterion",
                        "status_class", "row_class")
                }
        except (ValueError, TypeError, KeyError):
            pass
    previews = [x for x in out.splitlines()
                if x.startswith("QQ_BACKFILL_PROOF_FIRST_PREVIEW ")]
    if len(previews) == 1:
        counts = {}
        for field in COUNT_FIELDS:
            match = re.search(r"\b"+field+r"=(\d+)\b", previews[0])
            if match:
                counts[field] = int(match.group(1))
        report["preview_counts"] = counts
        if (returncode == 2 and
                "QQ_BACKFILL_PREVIEW_ONLY_NOT_COMMITTED" in out and
                all(k in counts for k in COUNT_FIELDS) and
                counts["blocked"] == 0 and
                counts["sheet_writes"] == 0 and
                counts["cursor_writes"] == 0):
            report["status"] = "PASS"
            report["exception_code"] = "NONE"
    return report


def summarize_uid_search_reply(status, rows):
    """Classify one IMAP SEARCH response without copying any untrusted data."""
    status_class = status if isinstance(status, str) and status in ("OK", "NO", "BAD") else "OTHER"
    if not isinstance(rows, (list, tuple)):
        row_class = "NON_SEQUENCE"
    elif not rows:
        row_class = "EMPTY_SEQUENCE"
    elif not isinstance(rows[0], bytes):
        row_class = "FIRST_NOT_BYTES"
    else:
        row_class = "BYTES"
    return {"status_class": status_class, "row_class": row_class}



def prioritize_inbox_mailboxes(mailboxes):
    """Deterministically inspect INBOX first without dropping other folders."""
    return sorted(mailboxes, key=lambda name: (
        0 if name.upper() == "INBOX" else 1, name.casefold()))
