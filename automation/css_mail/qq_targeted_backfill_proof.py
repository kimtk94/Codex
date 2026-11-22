#!/usr/bin/env python3
"""Read-only, bounded IMAP diagnostic for QQ historical invoice Backfill gaps.

No sheet writes, no cursor updates, no PDF body downloads and no identifiers
or amounts in stdout/CI artifact. Checking a source is NOT booking Revenue.
"""
from collections import Counter
import datetime as dt
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
import imaplib
import json
import os
from pathlib import Path
import re
import sys

SHEET = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
MAX_TARGETS = 35
ISSUED = re.compile(r"^\s*(?:❗️\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b", re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]", re.I)


def norm(x):
    return str(x or "").strip().upper()


def instant(x):
    try:
        t = dt.datetime.fromisoformat(str(x or "").replace("Z", "+00:00"))
        if t.tzinfo is None:
            raise ValueError()
        return t.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        raise ValueError("TIMESTAMP_UNVERIFIED") from None


def keyed(rows, name):
    if not rows or "invoice_number" not in rows[0]:
        raise ValueError(name + "_SCHEMA_MISSING")
    ret = {}
    for row in rows:
        key = norm(row.get("invoice_number"))
        if not key:
            continue
        if not re.fullmatch(r"\d{10,15}", key) or key in ret:
            raise ValueError(name + "_INVALID_OR_DUPLICATE_ID")
        ret[key] = row
    return ret


def pick_targets(qq_rows, css_rows, extract_rows, cursor_rows, audit_rows):
    """Return private in-memory 7/14/1 targets with no external writes."""
    qq = keyed(qq_rows, "QQ")
    css = keyed(css_rows, "CSS")
    extracts = keyed(extract_rows, "EXTRACT")
    inbox = [x for x in cursor_rows
             if str(x.get("year")) == "2026" and norm(x.get("folder")) == "INBOX"]
    audits = [x for x in audit_rows if str(x.get("year")) == "2026"]
    if len(inbox) != 1 or len(audits) != 1:
        raise ValueError("QQ_CURSOR_OR_AUDIT_NOT_UNIQUE")
    cursor, audit = inbox[0], audits[0]
    if not str(cursor.get("uidvalidity") or "").isdigit():
        raise ValueError("QQ_CURSOR_EPOCH_MISSING")
    if str(audit.get("status")) != "SCAN_COMPLETE":
        raise ValueError("QQ_SCAN_NOT_COMPLETE")
    scanned = instant(audit.get("last_run_utc"))
    try:
        last_uid = int(cursor["last_uid"])
        if last_uid <= 0:
            raise ValueError()
    except (ValueError, KeyError):
        raise ValueError("QQ_CURSOR_UID_INVALID") from None
    targets = []
    for number, evidence in extracts.items():
        if norm(evidence.get("validation_status")) != "FILENAME_PARSED":
            continue
        q = qq.get(number)
        if q is not None and not str(q.get("issued_month") or "").strip():
            category = "BLANK_ISSUED_MONTH"
        elif q is None and number not in css:
            collected = instant(evidence.get("extracted_at_utc"))
            try:
                uid = int(evidence.get("imap_uid") or "0")
            except ValueError:
                uid = 0
            if collected <= scanned and 0 < uid <= last_uid:
                category = "PRE_CURSOR_MISSING"
            elif collected > scanned and uid > last_uid:
                category = "POST_CURSOR_PENDING"
            else:
                category = "INCONSISTENT_CURSOR"
        else:
            continue
        targets.append({"category": category, "number": number,
                        "extract": evidence, "qq": q})
    if len(targets) > MAX_TARGETS:
        raise ValueError("TARGET_SCOPE_TOO_LARGE")
    return sorted(targets, key=lambda x: (x["category"], x["number"])), cursor, scanned


def original_mail_header(parts):
    payload = next((v[1] for v in parts or []
                    if isinstance(v, tuple) and len(v) > 1
                    and isinstance(v[1], bytes)), None)
    if not payload:
        return False
    header = BytesParser(policy=default).parsebytes(payload, headersonly=True)
    sender = parseaddr(str(header.get("From") or ""))[1].lower()
    subject = str(header.get("Subject") or "").strip()
    return (sender == "css@novogene-amea.com" and bool(ISSUED.match(subject))
            and not REPLY.match(subject)
            and not str(header.get("In-Reply-To") or "").strip())


def resolve_epoch(im):
    status, values = im.response("UIDVALIDITY")
    for v in values or []:
        raw = v.decode("ascii", "replace") if isinstance(v, bytes) else str(v)
        match = re.search(r"(?:UIDVALIDITY\s+)?([0-9]+)", raw, re.I)
        if match:
            return match.group(1)
    status, values = im.status('"INBOX"', "(UIDVALIDITY)")
    if status == "OK":
        for v in values or []:
            raw = v.decode("ascii", "replace") if isinstance(v, bytes) else str(v)
            match = re.search(r"UIDVALIDITY\s+([0-9]+)", raw, re.I)
            if match:
                return match.group(1)
    raise ValueError("IMAP_EPOCH_UNAVAILABLE")


def historical_backfill_search(im, year="2026", max_hits=120000):
    """Reproduce both original QQ Backfill subject searches, readonly.

    The candidate UID sets are kept private in process memory. Search results
    never appear in public artifacts or CI console output.
    """
    if year != "2026":
        raise ValueError("SEARCH_YEAR_NOT_ALLOWED")
    found = set()
    for phrase in ("Invoice Issued", "TAX INVOICE"):
        status, rows = im.uid(
            "SEARCH", None, "SINCE", "01-Jan-2026", "BEFORE", "01-Jan-2027",
            "SUBJECT", '"' + phrase + '"')
        if status != "OK" or not rows or not isinstance(rows[0], bytes):
            raise ValueError("BACKFILL_ORIGINAL_SEARCH_UNAVAILABLE")
        for token in rows[0].split():
            if not token.isdigit():
                raise ValueError("BACKFILL_ORIGINAL_SEARCH_INVALID_UID")
            found.add(token.decode("ascii"))
            if len(found) > max_hits:
                raise ValueError("BACKFILL_ORIGINAL_SEARCH_TOO_BROAD")
    return found


def classify_internaldate_response(status, parts):
    """Only classify fetch encoding; never expose or infer an Invoice issue date."""
    if status != "OK":
        return "FETCH_STATUS_ERROR"
    if not parts:
        return "EMPTY_RESPONSE"
    chunks = []
    for item in parts:
        if isinstance(item, bytes):
            chunks.append(item)
        elif isinstance(item, tuple):
            chunks.extend(v for v in item if isinstance(v, bytes))
    if not chunks:
        return "NO_BYTE_PAYLOAD"
    payload = b" ".join(chunks).decode("ascii", "replace")
    if "INTERNALDATE" not in payload.upper():
        return "DATE_TOKEN_ABSENT"
    match = re.search(
        r'INTERNALDATE\s+"(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2} [+-]\d{4})"',
        payload, re.I)
    if not match:
        # Classify only structure, never print or persist private IMAP values.
        if re.search(r'INTERNALDATE\s+NIL\b', payload, re.I):
            return "DATE_NIL"
        if re.search(r'INTERNALDATE\s+\d{1,2}-[A-Za-z]{3}-\d{4}', payload, re.I):
            return "DATE_UNQUOTED"
        if re.search(r'INTERNALDATE\s+"\d-[A-Za-z]{3}-\d{4}', payload, re.I):
            return "DATE_SINGLE_DIGIT_DAY"
        if re.search(r'INTERNALDATE\s+"\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2}', payload, re.I):
            return "DATE_COLON_TIMEZONE"
        if re.search(r'INTERNALDATE\s+\{\d+\}', payload, re.I):
            return "DATE_IMAP_LITERAL"
        return "DATE_FORMAT_OTHER"
    try:
        dt.datetime.strptime(match.group(1), "%d-%b-%Y %H:%M:%S %z")
        return "VALID_ARRIVAL_DATE"
    except ValueError:
        return "DATE_INVALID"


def extract_date_metadata(parts):
    """Mail arrival INTERNALDATE metadata only: NEVER the official issue date."""
    pieces = [v for item in parts or []
              for v in ((item if isinstance(item, bytes) else
                         b" ".join(x for x in item if isinstance(x, bytes))),)
              if v]
    text = b" ".join(pieces).decode("ascii", "replace")
    match = re.search(
        r'INTERNALDATE\s+"(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2} [+-]\d{4})"',
        text)
    if not match:
        return False
    try:
        dt.datetime.strptime(match.group(1), "%d-%b-%Y %H:%M:%S %z")
        return True
    except ValueError:
        return False


def parsed_matches(value, expected):
    if not value or value[5] != "FILENAME_PARSED":
        return False
    inv, h, po, project, amount, state = value
    e = expected
    try:
        positive = int(str(e.get("amount_krw") or "").strip())
    except ValueError:
        return False
    return (norm(inv) == norm(e.get("invoice_number"))
            and norm(h) == norm(e.get("h_project_number"))
            and norm(po) == norm(e.get("po_reference"))
            and norm(project) == norm(e.get("project_id"))
            and amount == positive and amount > 0)


def check_imap(targets, cursor, ingest, imap_factory, filenames, parser):
    """Use readonly EXAMINE and metadata-only FETCH; fail closed on missing UID epoch."""
    totals = Counter()
    # Stable zero-valued diagnostics make audit output and test assertions
    # independent of whether a particular failure category occurred.
    for label in ("original_mime_verified",
                  "historical_single_chunk_parser_would_match",
                  "fragmented_mime_legacy_parser_gap",
                  "blank_month_qq_extract_uid_conflict",
                  "imap_arrival_metadata_available",
                  "imap_arrival_metadata_unavailable",
                  "original_invoice_issue_date_proved",
                  "non_official_or_missing_header",
                  "mime_filename_or_identity_mismatch",
                  "cursor_inconsistent",
                  "ingest_metadata_missing",
                  "ingest_uid_or_epoch_conflict",
                  "mime_filename_missing",
                  "mime_fetch_unavailable"):
        totals[label] = 0
    totals.update({x["category"]: 0 for x in targets})
    totals["targeted"] = len(targets)
    if not targets:
        raise ValueError("NO_TARGETS_CHECK_SOURCE_FRESHNESS")
    with imap_factory("imap.exmail.qq.com", 993, timeout=60) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"], os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        status, _ = im.select("INBOX", readonly=True)
        if status != "OK":
            raise ValueError("IMAP_READONLY_SELECT_FAILED")
        if resolve_epoch(im) != str(cursor["uidvalidity"]):
            raise ValueError("IMAP_UIDVALIDITY_CHANGED")
        # Search uses the *original production criteria*; it is independent
        # from targeted MIME FETCH. This identifies search-filter vs
        # parser/cursor problems without advancing any persistent checkpoint.
        legacy_candidates = historical_backfill_search(im)
        totals["historical_search_verified"] = 1
        for target in targets:
            category = target["category"]
            totals[category] += 1
            uid_for_search = str(target["extract"].get("imap_uid", "")).strip()
            marker = ("search_matched_" if uid_for_search in legacy_candidates
                      else "search_absent_") + category.lower()
            totals[marker] += 1
            if category == "INCONSISTENT_CURSOR":
                totals["cursor_inconsistent"] += 1
                continue
            e = target["extract"]
            origin = ingest.get(norm(e.get("ingest_key")))
            if not origin:
                totals["ingest_metadata_missing"] += 1
                continue
            # Reconcile the two separate capture processes before IMAP fetch.
            if (norm(origin.get("folder")) != "INBOX"
                or str(origin.get("uidvalidity")) != str(cursor["uidvalidity"])
                or str(origin.get("imap_uid")) != str(e.get("imap_uid"))):
                totals["ingest_uid_or_epoch_conflict"] += 1
                continue
            uid = str(e.get("imap_uid"))
            if not uid.isdigit() or int(uid) <= 0:
                totals["invalid_source_uid"] += 1
                continue
            status, payload = im.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO)])")
            if status != "OK" or not original_mail_header(payload):
                totals["non_official_or_missing_header"] += 1
                continue
            totals["official_header_verified"] += 1
            status, payload = im.uid("FETCH", uid, "(BODYSTRUCTURE)")
            if status != "OK":
                totals["mime_fetch_unavailable"] += 1
                continue
            chunks = []
            for item in payload or []:
                if isinstance(item, bytes):
                    chunks.append(item)
                elif isinstance(item, tuple):
                    chunks.extend(x for x in item if isinstance(x, bytes))
            if not chunks:
                totals["mime_filename_missing"] += 1
                continue
            # Old incremental backfill checked each chunk separately.
            # The original issued proof reassembled fragmented MIME filenames.
            old_names = [name for part in chunks for name in filenames(part)]
            # IMAP tuple[0] may contain FETCH framing bytes between the actual
            # literal tuple[1] fragments. Joining all bytes can corrupt a
            # filename; first reassemble only literal payloads.
            literal_parts = [item[1] for item in payload or []
                             if isinstance(item, tuple) and len(item) > 1
                             and isinstance(item[1], bytes)]
            joined_names = filenames(b"".join(literal_parts)) if literal_parts else []
            joined_names += filenames(b" ".join(literal_parts)) if literal_parts else []
            joined_names += filenames(b"".join(chunks))
            joined_names += filenames(b" ".join(chunks))
            matching_old = any(parsed_matches(parser(n), e) for n in old_names)
            matching_joined = any(parsed_matches(parser(n), e) for n in joined_names)
            if not (matching_old or matching_joined):
                totals["mime_filename_or_identity_mismatch"] += 1
                continue
            totals["original_mime_verified"] += 1
            if matching_old:
                totals["historical_single_chunk_parser_would_match"] += 1
            elif matching_joined:
                totals["fragmented_mime_legacy_parser_gap"] += 1
            if category == "BLANK_ISSUED_MONTH":
                q = target["qq"]
                if norm(q.get("imap_uid")) != norm(e.get("imap_uid")):
                    totals["blank_month_qq_extract_uid_conflict"] += 1
                status, date_data = im.uid("FETCH", uid, "(INTERNALDATE)")
                date_state = classify_internaldate_response(status, date_data)
                totals["internaldate_" + date_state.lower()] += 1
                if date_state == "VALID_ARRIVAL_DATE":
                    totals["imap_arrival_metadata_available"] += 1
                else:
                    totals["imap_arrival_metadata_unavailable"] += 1
                # Mail arrival time is *not* an official invoice issue date.
                totals["original_invoice_issue_date_proved"] += 0
        im.logout()
    totals["business_writes"] = 0
    totals["qq_cursor_writes"] = 0
    totals["approved_canonical_promotions"] = 0
    return dict(sorted(totals.items()))


def main():
    # Explicitly read-only Sheets token; never import the Backfill writer module.
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    from qq_invoice_parity_audit import load_rows
    from invoice_provenance_triage import source_relevant_keys, load_ingest_subset
    from tax_invoice_extract import bodystructure_filenames, extract
    from qq_invoice_parity_audit import SHEET as DEFAULT_SHEET

    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["CKD_DRIVE_SA_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(creds)
    qq = load_rows(session, "QQ 2026 Invoice Backfill", 10000)
    css = load_rows(session, "CSS Tax Invoice List", 2000)
    extracts = load_rows(session, "CSS Tax Invoice Extract", 2000)
    cursor = load_rows(session, "QQ Backfill Cursor", 100)
    audit = load_rows(session, "QQ Backfill Audit", 100)
    targets, checkpoint, scan = pick_targets(qq, css, extracts, cursor, audit)
    needed = source_relevant_keys(qq, css, extracts)
    ingest = load_ingest_subset(session, DEFAULT_SHEET, needed)
    report = check_imap(
        targets, checkpoint, ingest, imaplib.IMAP4_SSL,
        bodystructure_filenames, extract)
    report["status"] = "HOLD"  # read-only evidence cannot authorize payment posting
    report["target_count"] = len(targets)
    report["scan_at"] = scan.isoformat()
    report["verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return report


if __name__ == "__main__":
    try:
        output = main()
        result = 2  # Known unlinked source data remains HOLD until approval.
    except Exception as err:
        output = {
            "status": "SOURCE_UNAVAILABLE" if isinstance(err, (OSError, KeyError, imaplib.IMAP4.error)) else "BLOCK",
            "error_code": str(err) if isinstance(err, ValueError) and
                          str(err) in {
                              "IMAP_UIDVALIDITY_CHANGED", "IMAP_EPOCH_UNAVAILABLE",
                              "INGEST_EVIDENCE_MISSING", "QQ_CURSOR_OR_AUDIT_NOT_UNIQUE",
                              "QQ_SCAN_NOT_COMPLETE", "TARGET_SCOPE_TOO_LARGE"
                          } else type(err).__name__,
            "business_writes": 0,
            "qq_cursor_writes": 0,
        }
        result = 2
    # All fields in output are safe aggregate counters / timestamps / status.
    target = os.getenv("QQ_TARGETED_PROOF_SUMMARY_PATH", "").strip()
    if target:
        Path(target).write_text(json.dumps(output, sort_keys=True) + "\n", encoding="utf-8")
    print("QQ_TARGETED_BACKFILL_PROOF " + json.dumps(output, sort_keys=True))
    sys.exit(result)
