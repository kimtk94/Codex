#!/usr/bin/env python3
"""Private-data-free, read-only Invoice provenance and ownership readiness triage.

Counts are diagnostic evidence, never financial posting instructions.
No network requests are made except the explicit read-only helper.
"""
import datetime as dt
from decimal import Decimal, InvalidOperation
import re
import urllib.parse

SHEET_INGEST = "CSS Git Ingest"
INGEST_FIELDS = ("ingest_key", "message_id", "imap_uid", "folder",
                 "uidvalidity", "received_at", "from_email", "recipient_to",
                 "cc", "subject", "amea_numbers", "h_project_numbers",
                 "sam_numbers", "batch_numbers", "fetched_at_utc", "direction",
                 "in_reply_to", "references")
OFFICIAL_SENDER = "css@novogene-amea.com"
NOTICE = re.compile(r"^\s*(?:❗️\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",
                    re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]", re.I)


def norm(value):
    return str(value or "").strip().upper()


def amount(value):
    raw = re.sub(r"[^0-9.-]", "", str(value or ""))
    try:
        x = Decimal(raw)
        if not x.is_finite() or x <= 0 or x != x.to_integral_value():
            raise ValueError()
        return int(x)
    except (InvalidOperation, ValueError):
        raise ValueError("INVOICE_GROSS_KRW_INVALID") from None


def identity_index(rows, label, field="invoice_number"):
    if not rows or field not in rows[0]:
        raise ValueError(label + "_SCHEMA_MISSING")
    result = {}
    for row in rows:
        key = norm(row.get(field))
        if not key:
            continue
        if key in result:
            raise ValueError(label + "_DUPLICATE_ID")
        result[key] = row
    return result


def _time(value):
    try:
        x = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if x.tzinfo is None:
            raise ValueError()
        return x.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        raise ValueError("SOURCE_TIME_INVALID") from None


def official_header(row, extract, cursor):
    if not row:
        return False
    return (norm(row.get("ingest_key")) == norm(extract.get("ingest_key"))
            and str(row.get("imap_uid") or "") == str(extract.get("imap_uid") or "")
            and str(row.get("uidvalidity") or "") == str(cursor.get("uidvalidity") or "")
            and norm(row.get("folder")) == "INBOX"
            and norm(row.get("direction")) == "INBOUND"
            and str(row.get("from_email") or "").strip().lower() == OFFICIAL_SENDER
            and bool(NOTICE.match(str(row.get("subject") or "")))
            and not REPLY.match(str(row.get("subject") or ""))
            and not str(row.get("in_reply_to") or "").strip())


def source_relevant_keys(qq_rows, css_rows, extract_rows):
    """Only require ingest evidence for missing or blank-month QQ records."""
    qq = identity_index(qq_rows, "QQ")
    css = identity_index(css_rows, "CSS")
    extracted = identity_index(extract_rows, "EXTRACT")
    keys = set()
    for number, row in extracted.items():
        q = qq.get(number)
        if (number not in qq and number not in css) or (
                q is not None and not str(q.get("issued_month") or "").strip()):
            key = norm(row.get("ingest_key"))
            if key:
                keys.add(key)
    return keys


def load_ingest_subset(session, spreadsheet_id, keys, bound=18000):
    """At most 2 readonly Sheets API GETs, not a 260k-cell ledger download."""
    if not keys:
        return {}
    prefix = "https://sheets.googleapis.com/v4/spreadsheets/" + spreadsheet_id
    addr = urllib.parse.quote("'CSS Git Ingest'!A1:A" + str(bound), safe="")
    index_response = session.get(prefix + "/values/" + addr, timeout=70)
    index_response.raise_for_status()
    entries = index_response.json().get("values", [])
    targets = {}
    for i, vals in enumerate(entries):
        if not vals:
            continue
        key = norm(vals[0])
        if key in keys:
            if key in targets:
                raise ValueError("INGEST_KEY_DUPLICATE")
            targets[key] = i + 1
    if len(targets) != len(keys):
        raise ValueError("INGEST_EVIDENCE_MISSING")
    # A second small batch request loads full metadata only for the 8+14
    # relevant rows; this does not fetch mail bodies or PDF attachments.
    ordered = sorted(targets.items(), key=lambda item: item[1])
    ranges = [("'CSS Git Ingest'!A%d:R%d" % (row, row)) for _, row in ordered]
    resp = session.get(prefix + "/values:batchGet",
                       params=[("ranges", v) for v in ranges], timeout=70)
    resp.raise_for_status()
    values = resp.json().get("valueRanges", [])
    if len(values) != len(ordered):
        raise ValueError("INGEST_BATCH_INCOMPLETE")
    result = {}
    for (key, _), chunk in zip(ordered, values):
        rows = chunk.get("values") or []
        if len(rows) != 1 or norm(rows[0][0]) != key:
            raise ValueError("INGEST_BATCH_KEY_MISMATCH")
        result[key] = dict(zip(INGEST_FIELDS, rows[0]))
    return result


def summarize(qq_rows, css_rows, extract_rows, cursor_rows,
              project_rows, tracker_rows, ingest_rows,
              scan_at, year="2026"):
    qq = identity_index(qq_rows, "QQ")
    css = identity_index(css_rows, "CSS")
    extracted = identity_index(extract_rows, "EXTRACT")
    if not cursor_rows or not {"year", "folder", "uidvalidity",
                              "last_uid"}.issubset(cursor_rows[0]):
        raise ValueError("CURSOR_SCHEMA_MISSING")
    cursors = [x for x in cursor_rows if str(x.get("year")) == year
               and norm(x.get("folder")) == "INBOX"]
    if len(cursors) != 1:
        raise ValueError("INBOX_CURSOR_MISSING_OR_DUPLICATE")
    cursor = cursors[0]
    try:
        current_uid = int(cursor["last_uid"])
        if current_uid <= 0 or not str(cursor.get("uidvalidity", "")).isdigit():
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("INBOX_CURSOR_INVALID") from None
    scan = _time(scan_at)
    if not project_rows or "project_id" not in project_rows[0]:
        raise ValueError("PROJECT_DASHBOARD_SCHEMA_MISSING")
    if not tracker_rows or "Responsible Sales" not in tracker_rows[0]:
        raise ValueError("SIF_TRACKER_OWNER_SCHEMA_MISSING")
    project_map = {}
    for row in project_rows:
        k = norm(row.get("project_id"))
        if k:
            project_map.setdefault(k, []).append(row)
    sales_map = {}
    for row in tracker_rows:
        k = norm(row.get("project_id") or row.get("AMEA No."))
        if k:
            sales_map.setdefault(k, []).append(row)
    lineage = {"qq_extract_overlap": 0, "four_key_match": 0,
               "field_conflict_or_missing": 0, "project_context_match": 0,
               "institution_context_present": 0,
               "sales_owner_candidate_present": 0,
               "sales_owner_candidate_ambiguous": 0,
               "owner_approval_verified": 0,
               "private_invoice_proof_receipts_verified": 0}
    blank = {"rows": 0, "uid_matches": 0, "uid_conflicts": 0,
             "other_fields_match": 0, "original_issue_month_verified": 0}
    missing = {"all_years_unlinked": 0, "cursor_prior_same_uid_epoch": 0,
               "cursor_after_same_uid_epoch": 0,
               "prior_official_header": 0, "after_official_header": 0,
               "unknown_uid_or_epoch": 0,
               "original_mime_proof_verified": 0}
    for number, e in extracted.items():
        q = qq.get(number)
        if number not in qq and number not in css:
            missing["all_years_unlinked"] += 1
            origin = ingest_rows.get(norm(e.get("ingest_key")))
            if not origin:
                missing["unknown_uid_or_epoch"] += 1
                continue
            if not official_header(origin, e, cursor):
                raise ValueError("INGEST_OFFICIAL_SOURCE_INCONSISTENT")
            uid = int(e.get("imap_uid") or "0")
            collected = _time(e.get("extracted_at_utc"))
            if uid <= current_uid:
                missing["cursor_prior_same_uid_epoch"] += 1
                if collected <= scan:
                    missing["prior_official_header"] += 1
            else:
                missing["cursor_after_same_uid_epoch"] += 1
                if collected > scan:
                    missing["after_official_header"] += 1
        if q is not None and not str(q.get("issued_month") or "").strip():
            blank["rows"] += 1
            origin = ingest_rows.get(norm(e.get("ingest_key")))
            if not official_header(origin, e, cursor):
                raise ValueError("BLANK_MONTH_INGEST_SOURCE_UNVERIFIED")
            if norm(q.get("imap_uid")) == norm(e.get("imap_uid")):
                blank["uid_matches"] += 1
            else:
                blank["uid_conflicts"] += 1
            if (amount(q.get("amount_krw")) == amount(e.get("amount_krw"))
                and all(norm(q.get(a)) == norm(e.get(b)) and norm(q.get(a))
                        for a,b in (("amea_project_id", "project_id"),
                                    ("h_project_id", "h_project_number"),
                                    ("po_reference", "po_reference")))):
                blank["other_fields_match"] += 1
        if q is None or number in css or not str(q.get("issued_month") or "").startswith(year + "-"):
            continue
        lineage["qq_extract_overlap"] += 1
        matching = (str(e.get("validation_status")) == "FILENAME_PARSED"
                    and amount(q.get("amount_krw")) == amount(e.get("amount_krw"))
                    and all(norm(q.get(a)) == norm(e.get(b)) and norm(q.get(a))
                            for a,b in (("amea_project_id", "project_id"),
                                        ("h_project_id", "h_project_number"),
                                        ("po_reference", "po_reference"),
                                        ("imap_uid", "imap_uid"))))
        if not matching:
            lineage["field_conflict_or_missing"] += 1
            continue
        lineage["four_key_match"] += 1
        key = norm(e.get("project_id"))
        project = project_map.get(key, [])
        if project:
            lineage["project_context_match"] += 1
        if any(norm(x.get("institution")) for x in project):
            lineage["institution_context_present"] += 1
        candidates = {norm(x.get("Responsible Sales"))
                      for x in sales_map.get(key, [])
                      if norm(x.get("Responsible Sales"))}
        if len(candidates) == 1:
            lineage["sales_owner_candidate_present"] += 1
        if len(candidates) > 1:
            lineage["sales_owner_candidate_ambiguous"] += 1
    return {"provenance_lineage": lineage,
            "blank_qq_month": blank,
            "unlinked_extract": missing,
            "provenance_owner_scope": "HOLD_NO_PER_RECORD_APPROVAL",
            "ingest_selected_read_only": True,
            "business_writes": 0}
