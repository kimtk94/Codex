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
