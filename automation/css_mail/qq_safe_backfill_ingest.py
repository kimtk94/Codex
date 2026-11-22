#!/usr/bin/env python3
"""Proof-first, side-effect-free QQ Backfill candidate evaluation.

This module does NOT update Google Sheets, IMAP mail or persistent cursors.
It is used by the writer only after source mailbox/UIDVALIDITY preflight.
"""
import datetime as dt
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
import re

from qq_cursor_checkpoint_policy import (
    conservative_cursor, RESOLVED
)

CSS_ISSUER = "css@novogene-amea.com"
ISSUED_SUBJECT = re.compile(
    r"^\s*(?:❗️\s*)?Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b", re.I
)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]", re.I)


def date_metadata_class(parts):
    """Only parse arrival metadata for aggregate diagnostics, never issue month."""
    blocks = []
    for item in parts or []:
        if isinstance(item, bytes):
            blocks.append(item)
        elif isinstance(item, tuple):
            blocks.extend(x for x in item if isinstance(x, bytes))
    message = b" ".join(blocks).decode("ascii", "replace")
    if "INTERNALDATE" not in message.upper():
        return "TOKEN_ABSENT"
    m = re.search(r'INTERNALDATE\s+"(\d{1,2}-[A-Za-z]{3}-\d{4} '
                  r'\d{2}:\d{2}:\d{2} [+-]\d{4})"', message, re.I)
    if not m:
        return "UNSUPPORTED_FORMAT"
    try:
        dt.datetime.strptime(m.group(1), "%d-%b-%Y %H:%M:%S %z")
        return "VALID_ARRIVAL_DATE"
    except ValueError:
        return "INVALID_ARRIVAL_DATE"


def original_notice_header(parts):
    if not parts:
        return None
    raw = next((item[1] for item in parts
                if isinstance(item, tuple) and len(item)>1
                and isinstance(item[1], bytes) and item[1]), None)
    if raw is None:
        return None
    try:
        parsed=BytesParser(policy=default).parsebytes(raw, headersonly=True)
        sender=parseaddr(str(parsed.get("From") or ""))[1].lower()
        subject=str(parsed.get("Subject") or "").strip()
        if not sender or not subject:
            return None
        if sender==CSS_ISSUER and ISSUED_SUBJECT.match(subject) and (
            not REPLY.match(subject)
            and not str(parsed.get("In-Reply-To") or "").strip()
        ):
            return subject
        # Complete, independently fetched header is proof the message is
        # not a new official issued notice, not evidence of an issued invoice.
        return False
    except (ValueError, TypeError):
        return None


def candidate_filenames(parts, get_chunks, read_names):
    chunks = get_chunks(parts)
    pieces = [item[1] for item in parts or []
              if isinstance(item, tuple) and len(item)>1
              and isinstance(item[1],bytes)]
    blocks = list(chunks)
    if pieces:
        blocks.extend((b"".join(pieces), b" ".join(pieces)))
    if chunks:
        blocks.extend((b"".join(chunks), b" ".join(chunks)))
    result = []
    for block in blocks:
        result.extend(read_names(block))
    return list(dict.fromkeys(result))


def evaluate_candidate(im, uid, folder, known_uid, get_chunks, read_names,
                       parse_filename, corroborate, source_rows):
    """Return (state, staged rows, diagnostics), never change source_rows.

    IMAP uses BODY.PEEK headers, BODYSTRUCTURE and INTERNALDATE only.
    An unresolved original issued notice blocks cursor advancement.
    """
    diag = {}
    if known_uid:
        return "KNOWN_UID_WITH_VALID_EVIDENCE", [], diag
    uid = str(uid)
    st, data = im.uid("FETCH", uid,
                      "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT IN-REPLY-TO)])")
    if st != "OK":
        return "FETCH_FAILED", [], diag
    subject = original_notice_header(data)
    if subject is None:
        return "ORIGINAL_HEADER_UNAVAILABLE", [], diag
    if subject is False:
        return "ORIGINAL_NONOFFICIAL_HEADER_VERIFIED", [], diag
    st, structures = im.uid("FETCH", uid, "(BODYSTRUCTURE)")
    if st != "OK" or not structures:
        return "FETCH_FAILED", [], diag
    names = candidate_filenames(structures, get_chunks, read_names)
    if not names:
        return "MIME_PARSER_UNRESOLVED", [], diag
    staged = {}
    failed = 0
    for name in names:
        parsed = parse_filename(name)
        if not parsed:
            parsed = corroborate(name, subject)
        if not parsed:
            failed += 1
            continue
        if len(parsed) != 6:
            return "MIME_PARSER_UNRESOLVED", [], diag
        inv, h, po, amea, gross, evidence = parsed
        if (not re.fullmatch(r"\d{8,15}", str(inv or ""))
            or not str(h or "").strip() or not str(po or "").strip()
            or not str(amea or "").strip() or not isinstance(gross,int)
            or gross <= 0 or evidence not in (
                "FILENAME_PARSED", "SUBJECT_CORROBORATED_FILENAME"
            )):
            return "MIME_PARSER_UNRESOLVED", [], diag
        row = [str(inv), "", str(gross), str(amea), str(h), str(po),
               folder, uid, name, evidence,
               dt.datetime.now(dt.timezone.utc).isoformat()]
        previous = source_rows.get(str(inv)) or staged.get(str(inv))
        if previous is not None and (
            len(previous) < 6 or
            [str(previous[i] or "").upper().strip() for i in (2,3,4,5)] !=
            [str(row[i] or "").upper().strip() for i in (2,3,4,5)]
        ):
            return "AMOUNT_CONFLICT", [], diag
        staged[str(inv)] = row
    if not staged:
        return "MIME_PARSER_UNRESOLVED", [], diag
    # If even one TAX INVOICE PDF candidate is malformed, don't silently
    # advance past potentially valid unrecorded invoices from this mail.
    if failed:
        tax_like = sum(
            "TAX" in n.upper() and "INVOICE" in n.upper() and ".PDF" in n.upper()
            for n in names
        )
        if tax_like > len(staged):
            return "MIME_PARSER_UNRESOLVED", [], diag
    st, arrival = im.uid("FETCH", uid, "(INTERNALDATE)")
    diag["arrival_metadata_state"] = (
        date_metadata_class(arrival) if st == "OK" else "FETCH_ERROR"
    )
    # The arrival date does not populate the QQ 'issued_month' column.
    return "ORIGINAL_ISSUED_PROOF_PERSISTED", list(staged.values()), diag


def safe_folder_checkpoint(start, processed_uids, outcomes):
    """Only advances to a proven contiguous prefix after data PUT succeeds."""
    return conservative_cursor(start, processed_uids, outcomes)
