#!/usr/bin/env python3
"""Backfill QQ IMAP thread headers into Q:R of existing CSS Git Ingest rows.

No mailbox mutations, no new mail rows, and no changes to columns A:P.
DRY_RUN=true by default. Require CSS_THREAD_BACKFILL_WRITE=true for writes.
"""
import datetime as dt
import imaplib
import json
import os
import sys
import urllib.parse
from email.parser import BytesParser
from email.policy import default

from incremental_sync import authorize, api, endpoint, TAB, COLS, folder_names

def read_values(session, region):
    rng = urllib.parse.quote("'" + TAB + "'!" + region, safe="")
    return api(session, "GET", endpoint("/values/" + rng)).get("values", [])

def plan(rows, folder, uidvalidity, *, scan_days=60, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=scan_days)
    selected = []
    for row_num, cells in enumerate(rows, start=2):
        cells = list(cells) + [""] * max(0, 18 - len(cells))
        key, uid, saved_folder, saved_validity = cells[0], cells[2], cells[3], cells[4]
        if not key or not uid or saved_folder != folder or saved_validity != uidvalidity:
            continue
        if key != folder + "|" + uidvalidity + "|" + uid:
            continue
        try:
            received = dt.datetime.fromisoformat(cells[5].replace("Z", "+00:00"))
            if received.tzinfo is None:
                continue
        except ValueError:
            continue
        if received < cutoff or cells[16] or cells[17]:
            continue
        selected.append((row_num, uid, cells[1]))
    return selected

def main():
    session = authorize()
    headers = read_values(session, "A1:R1")
    if not headers or headers[0] != COLS:
        raise RuntimeError("Expected A:R staging header; no writes")
    rows = read_values(session, "A2:R100000")
    limit = min(max(int(os.getenv("CSS_THREAD_BACKFILL_BATCH", "50")), 1), 100)
    days = min(max(int(os.getenv("CSS_IMAP_SCAN_DAYS", "60")), 1), 60)
    dry = os.getenv("DRY_RUN", "true").lower() != "false"
    writing = os.getenv("CSS_THREAD_BACKFILL_WRITE", "false").lower() == "true"
    if not dry and not writing:
        raise RuntimeError("Writing requires CSS_THREAD_BACKFILL_WRITE=true")
    updates, scanned, mismatched = [], 0, 0
    with imaplib.IMAP4_SSL("imap.exmail.qq.com", 993, timeout=45) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"], os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        folders = folder_names(im)
        sent = next((f for f,t in folders if "\\sent" in t or f.lower() in ("sent messages","sent","sent items")), None)
        if not sent:
            raise RuntimeError("Sent folder not found")
        for folder in ("INBOX", sent):
            status, _ = im.select('"' + folder.replace('"', '') + '"', readonly=True)
            if status != "OK":
                raise RuntimeError("Cannot select IMAP folder")
            _, result = im.response("UIDVALIDITY")
            if not result or not result[0]:
                raise RuntimeError("Missing UIDVALIDITY")
            validity = result[0].decode("ascii")
            pending = plan(rows, folder, validity, scan_days=days)
            for row_num, uid, existing_msg_id in pending[:max(0, limit-len(updates))]:
                status, data = im.uid("FETCH", uid.encode("ascii"),
                    "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)])")
                if status != "OK":
                    raise RuntimeError("IMAP FETCH failed; no writes")
                payload = next((x[1] for x in data or [] if isinstance(x, tuple) and isinstance(x[1], bytes)), None)
                if payload is None:
                    raise RuntimeError("IMAP header missing; no writes")
                msg = BytesParser(policy=default).parsebytes(payload, headersonly=True)
                current_msg_id = str(msg.get("Message-ID", "")).strip()
                if not existing_msg_id or current_msg_id != existing_msg_id.strip():
                    mismatched += 1
                    continue
                irt = str(msg.get("In-Reply-To", ""))[:500]
                refs = str(msg.get("References", ""))[:2000]
                scanned += 1
                if irt or refs:
                    updates.append({"range": "'" + TAB + "'!Q" + str(row_num) + ":R" + str(row_num),
                                    "values": [[irt, refs]]})
            if len(updates) >= limit:
                break
        im.logout()
    print(json.dumps({"dry_run":dry, "matched_messages":scanned,
        "thread_header_updates":len(updates), "message_id_mismatches":mismatched}))
    if not dry and updates:
        # Re-read target cells to avoid overwriting data filled by another sync.
        for item in updates:
            target = item["range"].split("!")[-1]
            current = read_values(session, target)
            if current and any(str(x).strip() for x in current[0]):
                raise RuntimeError("Target changed during scan; no writes")
        api(session, "POST", endpoint("/values:batchUpdate"),
            json={"valueInputOption":"RAW", "data": updates})

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("THREAD_BACKFILL_FAILED " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(1)
