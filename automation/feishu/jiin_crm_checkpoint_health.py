#!/usr/bin/env python3
"""Read-only CRM-only mailbox checkpoint and Feishu integrity snapshot.

A checkpoint shows durable scan progress, NOT proof the IMAP candidate list is
exhausted. Existing rows may predate the resumable runner, so row_count minus
checkpoint_saved is NOT interpreted as uncheckpointed work.
"""
import json
import os
import sys
import urllib.parse

import jiin_crm_filtered_ingest as c
from jiin_crm_full_scan import CHECKPOINT_TABLE, read_checkpoint
from jiin_crm_source_audit import summarize
from qq_mail_ingest import SafeError, auth, list_all
from setup_sales_web import EXPECTED_BASE


def assess(state, row_count, checkpoint_exists):
    scanned = int(state["scanned"])
    saved = int(state["saved"])
    uid = int(state["last_uid"])
    if min(scanned, saved, uid, row_count) < 0 or saved > scanned:
        raise SafeError("CRM_PROGRESS_INVALID_NUMBERS")
    if saved > row_count:
        raise SafeError("CRM_PROGRESS_SAVED_MORE_THAN_STORED")
    if scanned and not checkpoint_exists:
        raise SafeError("CRM_PROGRESS_MISSING_CHECKPOINT")
    if checkpoint_exists and not state["uidvalidity"]:
        raise SafeError("CRM_PROGRESS_MISSING_UIDVALIDITY")
    return {
        "checkpoint_present": checkpoint_exists,
        "last_scanned_uid": uid,
        "scanned_candidates_cumulative": scanned,
        "saved_by_checkpoint": saved,
        "stored_exact_sender_rows": row_count,
        "sender_date_duplicate_audit": "PASS",
        "full_scan_completion": "NOT_DETERMINABLE_FROM_CHECKPOINT",
        "source_mail_writes": 0,
        "feishu_writes": 0,
    }


def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("CRM_PROGRESS_WRONG_BASE")
    token, root = auth()
    tables = list_all(root + "/tables", token, "crm_progress_table_lookup")
    matches = {}
    for name in (c.TABLE, CHECKPOINT_TABLE):
        found = [t for t in tables if t.get("name") == name]
        if len(found) != 1:
            raise SafeError("CRM_PROGRESS_MISSING_OR_DUPLICATE_" + name.replace(" ", "_"))
        matches[name] = root + "/tables/" + urllib.parse.quote(found[0]["table_id"], safe="")
    count = summarize(list_all(matches[c.TABLE] + "/records", token, "crm_progress_mail_rows"))
    ident, state = read_checkpoint(token, matches[CHECKPOINT_TABLE])
    result = assess(state, count, bool(ident))
    print("CRM_CHECKPOINT_HEALTH_PASS " + json.dumps(result, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SafeError) else type(exc).__name__
        print("CRM_CHECKPOINT_HEALTH_FAILED=" + reason, file=sys.stderr)
        sys.exit(1)
