#!/usr/bin/env python3
"""Read ONLY exact crm@novogene.com sender mail from an authorized jiin mailbox.

Keeps a dedicated Feishu table and never changes existing QQ Mail Intake,
SFDC, billing, customer records or source mailbox state.
Credentials exclusively through GitHub Actions Secrets.
"""
import datetime as dt
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
import hashlib
import imaplib
import os
import re
import sys
import time
import urllib.parse

from qq_mail_ingest import SafeError, api, auth, list_all, get_fields, plain_field, decode_mail
from mail_classification_2026 import since_2026
from setup_sales_web import EXPECTED_BASE

ACCOUNT = "jiin.yoo@novogene.com"
SENDER = "crm@novogene.com"
TABLE = "CRM Filtered Mail Intake"
FIELDS = ("Mail Key", "Message ID", "Folder", "Direction", "Received At",
          "From", "To", "CC", "Subject", "Body Excerpt", "AMEA",
          "H Project", "Captured UTC", "In Reply To", "Source Account",
          "Source Filter")
BODY_LIMIT = 262144


def source_sender(header):
    """Exact From mailbox match, not substring or display name."""
    parsed = getaddresses([str(header or "")])
    if len(parsed) != 1:
        return False
    return parsed[0][1].strip().casefold() == SENDER


def mail_key(uidvalidity, uid):
    # QQ uses folder|UIDVALIDITY|UID. Namespacing prevents collisions.
    material = "CRM_ONLY|" + ACCOUNT + "|INBOX|" + uidvalidity + "|" + uid
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def open_mail():
    # Tencent Exmail (QQ enterprise mail) standard IMAP server.
    host = os.environ.get("JIIN_CRM_IMAP_HOST", "imap.exmail.qq.com").strip()
    if not host or any(c.isspace() for c in host):
        raise SafeError("JIIN_CRM_IMAP_HOST_NOT_CONFIGURED")
    port = int(os.environ.get("JIIN_CRM_IMAP_PORT", "993"))
    if not (1 <= port <= 65535):
        raise SafeError("JIIN_CRM_IMAP_PORT_INVALID")
    method = os.environ.get("JIIN_CRM_AUTH_METHOD", "app_password").strip().lower()
    if method not in ("oauth2", "app_password"):
        raise SafeError("JIIN_CRM_AUTH_METHOD_INVALID")
    if method == "oauth2":
        bearer = os.environ.get("JIIN_CRM_OAUTH_ACCESS_TOKEN", "")
        if not bearer:
            raise SafeError("JIIN_CRM_OAUTH_TOKEN_MISSING")
    else:
        password = os.environ.get("JIIN_CRM_APP_PASSWORD", "")
        if not password:
            raise SafeError("JIIN_CRM_APP_PASSWORD_MISSING")
    client = imaplib.IMAP4_SSL(host, port, timeout=40)
    try:
        if method == "oauth2":
            payload = ("user=" + ACCOUNT + "\x01auth=Bearer " + bearer + "\x01\x01").encode()
            status, _ = client.authenticate("XOAUTH2", lambda _: payload)
        else:
            status, _ = client.login(ACCOUNT, password)
        if status != "OK":
            raise SafeError("JIIN_CRM_IMAP_LOGIN_FAILED")
    except Exception:
        try:
            client.shutdown()
        except Exception:
            pass
        raise
    return client


def matching_candidates(im, indexed, cap):
    status, _ = im.select("INBOX", readonly=True)
    if status != "OK":
        raise SafeError("JIIN_CRM_INBOX_SELECT_FAILED")
    _, data = im.response("UIDVALIDITY")
    if not data or not data[0]:
        raise SafeError("JIIN_CRM_UIDVALIDITY_MISSING")
    uidvalidity = data[0].decode("ascii", "replace")
    # Server-side FROM filter reduces the header reads. Header parse below
    # enforces equality, because IMAP FROM SEARCH can use substring matching.
    status, data = im.uid("SEARCH", None, "SINCE", "31-Dec-2025", "FROM", '"'+SENDER+'"')
    if status != "OK":
        raise SafeError("JIIN_CRM_SEARCH_FAILED")
    all_uids = (data[0] or b"").split()
    unindexed = [uid for uid in all_uids if mail_key(uidvalidity, uid.decode("ascii")) not in indexed]
    print("CRM_FILTERED_SEARCH_CANDIDATES=" + str(len(all_uids)) +
          " unindexed=" + str(len(unindexed)))
    if not cap:
        return [], uidvalidity
    # Prefer latest, but rotate through history as new records are indexed.
    from qq_mail_ingest import select_uids
    uids = select_uids(unindexed, cap)
    result = []
    for uid in uids:
        status, parts = im.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM DATE MESSAGE-ID SUBJECT)])")
        if status != "OK":
            raise SafeError("JIIN_CRM_HEADER_FETCH_FAILED")
        header = next((part[1] for part in (parts or [])
                       if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
        if header is None:
            raise SafeError("JIIN_CRM_HEADER_MISSING")
        parsed = BytesParser(policy=default).parsebytes(header, headersonly=True)
        if not source_sender(parsed.get("From")):
            continue
        from qq_mail_ingest import date_string
        if not since_2026(date_string(parsed.get("Date"))):
            continue
        result.append(uid)
    print("CRM_FILTERED_EXACT_SENDER_HEADERS=" + str(len(result)))
    return result, uidvalidity


def decode_checked(payload, uidvalidity, uid):
    row = decode_mail(payload, "INBOX", "INBOUND", uidvalidity, uid)
    if not source_sender(row["From"]):
        raise SafeError("JIIN_CRM_BODY_SENDER_MISMATCH")
    if not since_2026(row.get("Received At")):
        raise SafeError("JIIN_CRM_BODY_DATE_MISMATCH")
    row["Mail Key"] = mail_key(uidvalidity, uid)
    row["Source Account"] = ACCOUNT
    row["Source Filter"] = "EXACT_FROM_CRM"
    return row


def ensure_table(token, root, allow_create):
    candidates = [t for t in list_all(root + "/tables", token, "crm_tables")
                  if t.get("name") == TABLE]
    if len(candidates) > 1:
        raise SafeError("CRM_DUPLICATE_TABLE")
    tid = candidates[0].get("table_id") if candidates else None
    if not tid and allow_create:
        data = api("POST", root + "/tables", token,
                   data={"table": {"name": TABLE, "default_view_name": "CRM 메일 전체",
                                   "fields": [{"field_name": name, "type": 1}
                                              for name in FIELDS]}},
                   action="crm_table_create")
        tid = (data.get("table") or {}).get("table_id") or data.get("table_id")
    if not tid:
        return None
    path = root + "/tables/" + urllib.parse.quote(tid, safe="")
    fields = {r.get("field_name"): r.get("type") for r in get_fields(token, path)}
    if any(fields.get(name) != 1 for name in FIELDS):
        raise SafeError("CRM_TABLE_SCHEMA_MISMATCH")
    return path


def run():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("CRM_UNEXPECTED_FEISHU_BASE")
    mode = os.environ.get("JIIN_CRM_MODE", "probe").strip().lower()
    if mode not in ("probe", "apply", "backfill"):
        raise SafeError("CRM_MODE_INVALID")
    limit = int(os.environ.get(
        "JIIN_CRM_MAIL_LIMIT", "15000" if mode == "backfill" else "300"))
    if not (1 <= limit <= (15000 if mode == "backfill" else 1000)):
        raise SafeError("CRM_MAIL_LIMIT_INVALID")
    token, root = auth()
    if mode in ("apply", "backfill"):
        # The full scan uses an idempotent UID checkpoint. Scheduled jobs
        # process up to 300 more candidates; explicit backfills drain 15,000.
        from jiin_crm_full_scan import drain
        return drain(token, root, limit)
    # Probe checks authorized login only: no mailbox headers or Feishu writes.
    im = open_mail()
    try:
        print("CRM_AUTH_PROBE_PASS read_headers=0 writes=0")
    finally:
        try:
            im.logout()
        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError):
            pass


if __name__ == "__main__":
    try:
        run()
    except (SafeError, ValueError, imaplib.IMAP4.error) as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("CRM_FILTERED_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
