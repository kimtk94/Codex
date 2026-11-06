#!/usr/bin/env python3
"""Read-only original MIME verification of high-priority PO body claims.

The Feishu Body Excerpt is limited to the first 1,800 normalized characters.
Re-open only high-priority original mails using source Mail Key -> current
UIDVALIDITY + UID. Never guess project links, mutate mail flags, download
files to disk, claim signed-file verification, or emit private content in logs.

Each MIME fetch is byte-bounded. Oversize/partial originals are counted as
incomplete and never treated as verified.
"""
from collections import Counter
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
import html
import imaplib
import json
import os
import re
import sys
import urllib.parse

import jiin_crm_filtered_ingest as crm
import contract_po_tracker as po
import po_body_multiplicity_audit as audit
import qq_mail_ingest as qq
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from setup_sales_web import EXPECTED_BASE

MAX_MIME_BYTES = 1048576
MAX_BODY_CHARS = 200000
PRIORITY = {
    "BODY_DELIVERY_CLAIM_REVIEW",
    "BODY_APPROVAL_CLAIM_REVIEW",
    "BODY_MISSING_OR_NOT_RECEIVED_CANDIDATE",
}


def targets(source, owned_contracts=None):
    """If provided, restrict MIME work to CSS-verified Contract project IDs."""
    selected = {}
    flagged = Counter()
    for name, sender in po.SOURCES:
        rows = {}
        for item in source.get(name, []):
            fields = item.get("fields") or {}
            event = audit.classify(fields, sender, name)
            if not event:
                continue
            if owned_contracts is not None:
                project = event["project"]
                received = po.parse_time(plain_field(fields.get("Received At")))
                if (project not in owned_contracts or not received
                        or received <= owned_contracts[project]):
                    continue
            if event["body_signal"] not in PRIORITY and not event["body_near_excerpt_limit"]:
                continue
            key = event["key"]
            if key in rows:
                raise SafeError("PO_ORIGINAL_DUPLICATE_MAIL_KEY")
            rows[key] = fields
            flagged["source_" + ("CRM" if sender == po.CRM_SENDER else "CSS")] += 1
        selected[name] = rows
    return selected, flagged


def normalized_sender(value):
    addresses = getaddresses([str(value or "")])
    return {email.strip().lower() for _,email in addresses if email}


def extract_raw_body(message):
    """Decode complete text/plain or fallback HTML; keep quote line breaks."""
    best_html = None
    for part in message.walk():
        if part.get_content_disposition() == "attachment" or part.get_filename():
            continue
        if part.get_content_type() not in ("text/plain", "text/html"):
            continue
        try:
            value = part.get_content()
        except (ValueError, TypeError, UnicodeError, LookupError, AssertionError):
            continue
        if not isinstance(value, str):
            continue
        if part.get_content_type() == "text/plain":
            return value[:MAX_BODY_CHARS]
        if best_html is None:
            best_html = value
    if best_html:
        parser = qq.HtmlToText()
        try:
            parser.feed(best_html)
            return html.unescape(" ".join(parser.fragments))[:MAX_BODY_CHARS]
        except (ValueError, TypeError):
            pass
    return ""


def inspect_message(raw, expected, source, total_size=None):
    """Never claim documentary receipt based on message text or MIME hints."""
    msg = BytesParser(policy=default).parsebytes(raw)
    header_sender = normalized_sender(msg.get("From"))
    if header_sender != {source}:
        raise SafeError("PO_ORIGINAL_SENDER_MISMATCH")
    if not po.since_2026(qq.date_string(msg.get("Date"))):
        raise SafeError("PO_ORIGINAL_DATE_MISMATCH")
    stored_id = plain_field(expected.get("Message ID")).strip()
    raw_id = str(msg.get("Message-ID") or "").strip()
    if stored_id and raw_id and stored_id != raw_id:
        raise SafeError("PO_ORIGINAL_MESSAGE_ID_MISMATCH")
    incomplete = total_size is None or total_size > len(raw)
    body = extract_raw_body(msg)
    # Signatures and quoted prior emails can contain misleading PO statements.
    quoted = bool(audit.QUOTE.search(body))
    mime_files = sum(
        bool(part.get_filename() or part.get_content_disposition() == "attachment")
        for part in msg.walk() if not part.is_multipart()
    )
    signal = audit.body_signal(body)
    return {
        "complete_mime": not incomplete,
        "full_body_chars": len(body),
        "raw_body_signal": signal,
        "quoted_content": quoted,
        "body_longer_than_excerpt": len(body) > len(plain_field(expected.get("Body Excerpt"))),
        "attachment_mime_part_seen": mime_files > 0,
        "body_limit_reached": len(body) >= MAX_BODY_CHARS,
        "identity_validated": True,
    }


def open_source(name):
    if name == "CRM Filtered Mail Intake":
        return crm.open_mail()
    if name != "QQ Mail Intake":
        raise SafeError("PO_ORIGINAL_UNKNOWN_SOURCE")
    user = qq.required("CSS_QQ_MAIL_ADDRESS")
    password = qq.required("CSS_QQ_MAIL_AUTH_CODE")
    im = imaplib.IMAP4_SSL("imap.exmail.qq.com", 993, timeout=40)
    try:
        if im.login(user, password)[0] != "OK":
            raise SafeError("PO_ORIGINAL_CSS_LOGIN_FAILED")
    except Exception:
        try:
            im.logout()
        except Exception:
            pass
        raise
    return im


def lookup_key(name, validity, uid):
    if name == "CRM Filtered Mail Intake":
        return crm.mail_key(validity, uid)
    return qq.key("INBOX", validity, uid)


def verify_source(name, source, selected):
    """One SEARCH per account, then bounded PEEK fetch only for known keys."""
    result = Counter()
    if not selected:
        return result
    im = open_source(name)
    try:
        status, _ = im.select("INBOX", readonly=True)
        if status != "OK":
            raise SafeError("PO_ORIGINAL_INBOX_SELECT_FAILED")
        _, value = im.response("UIDVALIDITY")
        if not value or not value[0]:
            raise SafeError("PO_ORIGINAL_UIDVALIDITY_MISSING")
        validity = value[0].decode("ascii", "replace")
        status, data = im.uid("SEARCH", None, "SINCE", "31-Dec-2025")
        if status != "OK":
            raise SafeError("PO_ORIGINAL_UID_SEARCH_FAILED")
        matched = set()
        for raw_uid in (data[0] or b"").split():
            uid = raw_uid.decode("ascii")
            key = lookup_key(name, validity, uid)
            if key not in selected:
                continue
            if key in matched:
                raise SafeError("PO_ORIGINAL_DUPLICATE_UID")
            matched.add(key)
            response, parts = im.uid(
                "FETCH", uid,
                "(RFC822.SIZE BODY.PEEK[]<0." + str(MAX_MIME_BYTES) + ">)"
            )
            if response != "OK":
                raise SafeError("PO_ORIGINAL_FETCH_FAILED")
            pair = next((x for x in (parts or [])
                         if isinstance(x, tuple) and len(x) >= 2
                         and isinstance(x[1], bytes)), None)
            if not pair:
                raise SafeError("PO_ORIGINAL_FETCH_EMPTY")
            m = re.search(rb"RFC822.SIZE\s+(\d+)", pair[0])
            total_size = int(m.group(1)) if m else None
            rec = inspect_message(pair[1], selected[key], source, total_size)
            result["fetched"] += 1
            for attr in ("complete_mime", "quoted_content",
                         "body_longer_than_excerpt", "attachment_mime_part_seen",
                         "body_limit_reached"):
                result[attr] += int(rec[attr])
            result["signal_" + rec["raw_body_signal"]] += 1
        result["missing_uid_or_changed_validity"] = len(selected) - len(matched)
    finally:
        try:
            im.logout()
        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError):
            pass
    return result


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("PO_ORIGINAL_WRONG_BASE")
    token, root = auth()
    tables = list_all(root+"/tables", token, "po_original_tables")
    source = {}
    for name, sender in po.SOURCES:
        path = po.find_source(token, root, tables, name)
        source[name] = list_all(path+"/records", token, "po_original_source")
    # CRM-only Contract announcements belong to other sales and must never
    # expand the user's PO original-mail verification work.
    tracker_matches = [t for t in tables if t.get("name") == po.TABLE]
    if len(tracker_matches) != 1:
        raise SafeError("PO_ORIGINAL_TRACKER_NOT_UNIQUE")
    tracker_path = root + "/tables/" + urllib.parse.quote(
        tracker_matches[0]["table_id"], safe=""
    )
    owned_contracts = {}
    for rec in list_all(tracker_path + "/records", token, "po_original_owned_contracts"):
        fields = rec.get("fields") or {}
        scope = plain_field(fields.get("Contract Scope")).strip()
        if scope == "EXCLUDED_NOT_MY_CSS_CONTRACT":
            continue
        if scope != "MY_CSS_CONTRACT" or plain_field(fields.get("Contract Source")) != "CSS":
            raise SafeError("PO_ORIGINAL_CONTRACT_OWNERSHIP_UNVERIFIED")
        project = plain_field(fields.get("Project ID")).strip()
        created = po.parse_time(plain_field(fields.get("Contract Notice UTC")))
        if not project or not created or project in owned_contracts:
            raise SafeError("PO_ORIGINAL_DUPLICATE_OR_INVALID_CSS_CONTRACT")
        owned_contracts[project] = created
    selected, flagged = targets(source, owned_contracts)
    stats = {}
    for name, sender in po.SOURCES:
        stats["CRM" if sender == po.CRM_SENDER else "CSS"] = dict(
            verify_source(name, sender, selected[name]))
    output = {
        "owned_css_contract_projects": len(owned_contracts),
        "candidate_mail_count": sum(len(x) for x in selected.values()),
        "candidate_sources": dict(flagged),
        "source_results": stats,
        "mode": "IMAP_READONLY_PEEK_BOUND_1MB",
        "body_limit_characters": MAX_BODY_CHARS,
        "document_receipt_verified": 0,
        "manual_links": 0,
        "source_writes": 0,
    }
    print("PO_ORIGINAL_MIME_REVIEW_PASS "+json.dumps(output, sort_keys=True))
    return output


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("PO_ORIGINAL_MIME_REVIEW_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
