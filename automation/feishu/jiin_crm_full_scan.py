#!/usr/bin/env python3
"""Resumable full 2026 CRM-only mail scan, with fail-closed Feishu UID checkpoint.

Only headers matching exact From crm@novogene.com are fetched in full.
All 2026 candidates are examined once (including rejected From headers).
The durable cursor is advanced ONLY after acknowledged, verified Feishu writes.
This deliberately does not send mail or mutate source Inbox, QQ Mail Intake,
SFDC, Revenue or existing non-CRM business tables.
"""
import datetime as dt
from email.parser import BytesParser
from email.policy import default
import imaplib
import os
import re
import time
import urllib.parse

import jiin_crm_filtered_ingest as c
from qq_mail_ingest import SafeError, api, get_fields, list_all, plain_field
from mail_classification_2026 import since_2026
from qq_mail_ingest import date_string

CHECKPOINT_TABLE = "CRM Filtered Mail Scan State"
CHECKPOINT_KEY = "jiin-2026-exact-crm-from-inbox"
CHECKPOINT_FIELDS = ("Checkpoint Key", "UIDVALIDITY", "Last Scanned UID",
                     "Scanned UTC", "Scanned Candidates", "Saved CRM Mail")
PER_SESSION = 200
MAX_CANDIDATES = 15000
MAX_CONSECUTIVE_ABORTS = 4


def ensure_checkpoint(token, root):
    tables = list_all(root + "/tables", token, "crm_progress_tables")
    matches = [t for t in tables if t.get("name") == CHECKPOINT_TABLE]
    if len(matches) > 1:
        raise SafeError("CRM_PROGRESS_DUPLICATE_TABLE")
    tid = matches[0].get("table_id") if matches else None
    if not tid:
        result = api("POST", root + "/tables", token, data={"table": {
            "name": CHECKPOINT_TABLE, "default_view_name": "Scan State",
            "fields": [{"field_name": f, "type": 1} for f in CHECKPOINT_FIELDS]
        }}, action="crm_progress_table_create")
        tid = (result.get("table") or {}).get("table_id") or result.get("table_id")
    if not tid:
        raise SafeError("CRM_PROGRESS_TABLE_NOT_CREATED")
    path = root + "/tables/" + urllib.parse.quote(tid, safe="")
    schema = {f.get("field_name"): f.get("type") for f in get_fields(token, path)}
    if any(schema.get(f) != 1 for f in CHECKPOINT_FIELDS):
        raise SafeError("CRM_PROGRESS_SCHEMA_MISMATCH")
    return path


def read_checkpoint(token, path):
    matches = [
        r for r in list_all(path + "/records", token, "crm_progress_read")
        if plain_field((r.get("fields") or {}).get("Checkpoint Key")) == CHECKPOINT_KEY
    ]
    if len(matches) > 1:
        raise SafeError("CRM_PROGRESS_DUPLICATE_CHECKPOINT")
    if not matches:
        return None, {"uidvalidity": "", "last_uid": 0, "scanned": 0, "saved": 0}
    r = matches[0]
    fields = r.get("fields") or {}
    try:
        state = {
            "uidvalidity": plain_field(fields.get("UIDVALIDITY")),
            "last_uid": int(plain_field(fields.get("Last Scanned UID")) or "0"),
            "scanned": int(plain_field(fields.get("Scanned Candidates")) or "0"),
            "saved": int(plain_field(fields.get("Saved CRM Mail")) or "0"),
        }
    except ValueError:
        raise SafeError("CRM_PROGRESS_CORRUPT_NUMBERS")
    if min(state["last_uid"], state["scanned"], state["saved"]) < 0:
        raise SafeError("CRM_PROGRESS_NEGATIVE_NUMBER")
    return r.get("record_id"), state


def write_checkpoint(token, path, record_id, validity, last_uid, scanned, saved):
    fields = {
        "Checkpoint Key": CHECKPOINT_KEY,
        "UIDVALIDITY": validity,
        "Last Scanned UID": str(last_uid),
        "Scanned UTC": dt.datetime.now(dt.timezone.utc).isoformat(),
        "Scanned Candidates": str(scanned),
        "Saved CRM Mail": str(saved),
    }
    endpoint = path + "/records"
    if record_id:
        endpoint += "/" + urllib.parse.quote(record_id, safe="")
    result = api("PUT" if record_id else "POST", endpoint, token,
                 data={"fields": fields}, action="crm_progress_write")
    ident = (result.get("record") or {}).get("record_id")
    if not ident or (record_id and ident != record_id):
        raise SafeError("CRM_PROGRESS_WRITE_UNVERIFIED")
    # Read back the checkpoint, rather than treating an HTTP 200 as committed.
    chk = api("GET", path + "/records/" + urllib.parse.quote(ident, safe=""),
              token, action="crm_progress_readback")
    actual = (chk.get("record") or {}).get("fields") or {}
    for field, expected in fields.items():
        if field == "Scanned UTC":
            continue
        if plain_field(actual.get(field)).strip() != expected:
            raise SafeError("CRM_PROGRESS_READBACK_MISMATCH")
    return ident


def search_next(im, last_uid, count, saved_validity):
    status, _ = im.select("INBOX", readonly=True)
    if status != "OK":
        raise SafeError("CRM_SCAN_INBOX_SELECT_FAILED")
    _, val = im.response("UIDVALIDITY")
    if not val or not val[0]:
        raise SafeError("CRM_SCAN_UIDVALIDITY_MISSING")
    validity = val[0].decode("ascii", "replace")
    if saved_validity and saved_validity != validity:
        raise SafeError("CRM_SCAN_UIDVALIDITY_CHANGED_REVIEW_REQUIRED")
    status, data = im.uid("SEARCH", None, "SINCE", "31-Dec-2025",
                          "FROM", '"' + c.SENDER + '"')
    if status != "OK":
        raise SafeError("CRM_SCAN_IMAP_SEARCH_FAILED")
    try:
        # Exhaustive ASCENDING UID order prevents repeatedly rechecking rejects.
        candidates = sorted(set(int(k) for k in (data[0] or b"").split()))
    except ValueError:
        raise SafeError("CRM_SCAN_INVALID_UID")
    if any(n <= 0 for n in candidates):
        raise SafeError("CRM_SCAN_UID_NONPOSITIVE")
    pending = [uid for uid in candidates if uid > last_uid]
    print("CRM_SCAN_SEARCH_TOTAL=" + str(len(candidates)) +
          " pending=" + str(len(pending)) +
          " limit=" + str(count), flush=True)
    return validity, pending[:count], len(pending)


def selected_mail(im, uid, validity, indexed):
    str_uid = str(uid)
    status, parts = im.uid(
        "FETCH", str_uid,
        "(BODY.PEEK[HEADER.FIELDS (FROM DATE MESSAGE-ID SUBJECT)])"
    )
    if status != "OK":
        raise SafeError("CRM_SCAN_HEADER_FETCH_FAILED")
    payload = next((part[1] for part in (parts or [])
                    if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
    if payload is None:
        raise SafeError("CRM_SCAN_HEADER_EMPTY")
    msg = BytesParser(policy=default).parsebytes(payload, headersonly=True)
    if not c.source_sender(msg.get("From")):
        return None
    if not since_2026(date_string(msg.get("Date"))):
        return None
    key = c.mail_key(validity, str_uid)
    if key in indexed:
        return None
    status, parts = im.uid("FETCH", str_uid,
                           "(BODY.PEEK[]<0." + str(c.BODY_LIMIT) + ">)")
    if status != "OK":
        raise SafeError("CRM_SCAN_BODY_FETCH_FAILED")
    body = next((part[1] for part in (parts or [])
                 if isinstance(part, tuple) and isinstance(part[1], bytes)), None)
    if body is None:
        raise SafeError("CRM_SCAN_BODY_EMPTY")
    # Body header is revalidated; a changed sender is a hard failure, not a skip.
    return c.decode_checked(body, validity, str_uid)


def _reconcile_after_http400(token, path, indexed):
    """Check Feishu readback before any retry; never assume 400 means no write.

    The batch may have been committed before a gateway error. Only Mail Key
    hashes are inspected and no customer content is included in logs.
    """
    records = list_all(path + "/records", token, "crm_scan_400_readback")
    seen = {}
    for item in records:
        key = plain_field((item.get("fields") or {}).get("Mail Key")).strip()
        if not key:
            continue
        if key in seen or not item.get("record_id"):
            raise SafeError("CRM_SCAN_400_DUPLICATE_OR_MISSING_ID")
        seen[key] = item["record_id"]
    indexed.update(seen)


def _remove_invalid_controls(row):
    """Replace only unsupported Unicode control code points, not content."""
    clean = {}
    count = 0
    for name, value in row.items():
        if not isinstance(value, str):
            clean[name] = value
            continue
        new = []
        for ch in value:
            cp = ord(ch)
            bad = (cp < 32 and ch not in "\t\n\r") or (127 <= cp <= 159)
            bad = bad or (0xD800 <= cp <= 0xDFFF) or cp in (0xFFFE, 0xFFFF)
            if bad:
                new.append(" ")
                count += 1
            else:
                new.append(ch)
        clean[name] = "".join(new)
    return clean, count


def persist_batch(token, path, rows, indexed):
    """Idempotent 400 recovery: reconcile, bisect, then fail closed on a row."""
    if not rows:
        return 0
    if len(rows) > 25:
        raise SafeError("CRM_SCAN_BATCH_OVER_LIMIT")
    keys = [r.get("Mail Key") for r in rows]
    if len(set(keys)) != len(rows) or any(not k for k in keys):
        raise SafeError("CRM_SCAN_BATCH_DUPLICATE_OR_EMPTY_KEY")
    pending = [row for row in rows if row["Mail Key"] not in indexed]
    if not pending:
        return 0
    try:
        result = api("POST", path + "/records/batch_create", token,
                     data={"records": [{"fields": row} for row in pending]},
                     action="crm_scan_batch_create")
    except SafeError as exc:
        if "crm_scan_batch_create_HTTP_400" not in str(exc):
            raise
        # Feishu can reject a large batch or a single malformed string.
        # Read back committed rows before retrying to avoid duplicate Mail Keys.
        _reconcile_after_http400(token, path, indexed)
        remaining = [row for row in pending if row["Mail Key"] not in indexed]
        if not remaining:
            print("CRM_SCAN_HTTP400_RECONCILED rows=" + str(len(pending)), flush=True)
            return 0
        if len(remaining) == 1:
            safe_row, replaced = _remove_invalid_controls(remaining[0])
            if replaced:
                print("CRM_SCAN_HTTP400_CONTROL_REPLACEMENTS=" + str(replaced),
                      flush=True)
                try:
                    result = api("POST", path + "/records/batch_create", token,
                                 data={"records": [{"fields": safe_row}]},
                                 action="crm_scan_control_fallback")
                except SafeError:
                    raise SafeError("CRM_SCAN_SINGLE_ROW_400_REQUIRES_REVIEW") from None
                stored = result.get("records") or []
                if len(stored) != 1 or not stored[0].get("record_id"):
                    raise SafeError("CRM_SCAN_CONTROL_FALLBACK_UNVERIFIED")
                indexed[safe_row["Mail Key"]] = stored[0]["record_id"]
                return 1
            raise SafeError("CRM_SCAN_SINGLE_ROW_400_REQUIRES_REVIEW") from None
        mid = len(remaining) // 2
        print("CRM_SCAN_HTTP400_SPLIT size=" + str(len(remaining)), flush=True)
        left = persist_batch(token, path, remaining[:mid], indexed)
        right = persist_batch(token, path, remaining[mid:], indexed)
        return left + right
    records = result.get("records") or []
    if len(records) != len(pending) or any(not r.get("record_id") for r in records):
        raise SafeError("CRM_SCAN_FEISHU_SAVE_UNVERIFIED")
    for row, item in zip(pending, records):
        indexed[row["Mail Key"]] = item["record_id"]
    return len(pending)


def scan_block(im, token, mail_path, state_path, checkpoint_id, state, indexed, cap):
    validity, candidates, pending = search_next(
        im, state["last_uid"], min(cap, PER_SESSION), state["uidvalidity"])
    if not candidates:
        return checkpoint_id, state, 0, pending, True
    writes = []
    added = 0
    for uid in candidates:
        row = selected_mail(im, uid, validity, indexed)
        if row is not None:
            writes.append(row)
        if len(writes) == 25:
            added += persist_batch(token, mail_path, writes, indexed)
            writes = []
    added += persist_batch(token, mail_path, writes, indexed)
    # The progress marker advances only AFTER all accepted bodies are stored.
    new_scanned = state["scanned"] + len(candidates)
    new_saved = state["saved"] + added
    checkpoint_id = write_checkpoint(
        token, state_path, checkpoint_id, validity,
        candidates[-1], new_scanned, new_saved)
    state = {"uidvalidity": validity, "last_uid": candidates[-1],
             "scanned": new_scanned, "saved": new_saved}
    print("CRM_SCAN_BLOCK_PASS checked=" + str(len(candidates)) +
          " added=" + str(added) + " cursor_advanced=1" +
          " scanned_total=" + str(new_scanned) +
          " added_total=" + str(new_saved), flush=True)
    return checkpoint_id, state, len(candidates), pending - len(candidates), False


def drain(token, root, max_candidates):
    if not (1 <= max_candidates <= MAX_CANDIDATES):
        raise SafeError("CRM_SCAN_INVALID_MAX_CANDIDATES")
    mail_path = c.ensure_table(token, root, allow_create=True)
    state_path = ensure_checkpoint(token, root)
    old = list_all(mail_path + "/records", token, "crm_existing")
    indexed = {}
    for record in old:
        key = plain_field((record.get("fields") or {}).get("Mail Key"))
        if key:
            if key in indexed:
                raise SafeError("CRM_SCAN_DUPLICATE_SOURCE_KEY")
            indexed[key] = record.get("record_id")
    checkpoint_id, state = read_checkpoint(token, state_path)
    attempted = 0
    consecutive_abort = 0
    stopped_complete = False
    while attempted < max_candidates:
        im = None
        try:
            im = c.open_mail()
            checkpoint_id, state, processed, pending, complete = scan_block(
                im, token, mail_path, state_path, checkpoint_id, state, indexed,
                max_candidates - attempted)
            attempted += processed
            consecutive_abort = 0
            if complete or pending == 0:
                stopped_complete = True
                break
        except (imaplib.IMAP4.abort, OSError) as exc:
            consecutive_abort += 1
            if consecutive_abort > MAX_CONSECUTIVE_ABORTS:
                raise SafeError("CRM_SCAN_IMAP_RETRIES_EXHAUSTED") from None
            print("CRM_SCAN_IMAP_RETRY=" + str(consecutive_abort), flush=True)
            time.sleep(min(40, 10 * consecutive_abort))
            # Even after partial acknowledgement, the cursor is advanced only
            # on an entirely successful block; reload state and saved keys.
            checkpoint_id, state = read_checkpoint(token, state_path)
            records = list_all(mail_path + "/records", token,
                               "crm_scan_reconnect_index")
            indexed = {}
            for record in records:
                key = plain_field((record.get("fields") or {}).get("Mail Key"))
                if key:
                    if key in indexed:
                        raise SafeError("CRM_SCAN_DUPLICATE_KEY_AFTER_RECONNECT")
                    indexed[key] = record.get("record_id")
        finally:
            if im is not None:
                try:
                    im.logout()
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError):
                    pass
    print("CRM_FULL_SCAN_RESULT checked_this_run=" + str(attempted) +
          " scanned_cumulative=" + str(state["scanned"]) +
          " saved_by_checkpoint=" + str(state["saved"]) +
          " mail_rows_now=" + str(len(indexed)) +
          " all_candidates_scanned=" + str(stopped_complete) +
          " source_mailbox_writes=0 other_table_writes=0", flush=True)
    return {"checked": attempted, "complete": stopped_complete,
            "saved": len(indexed), "last_uid": state["last_uid"]}
