#!/usr/bin/env python3
"""Converge SFDC's read-only unanswered-mail projection to the live QQ snapshot.

Only SFDC Unanswered Emails A:U is replaced. The review Decision ledger is
append-only by UID (NONE placeholders only); explicit choices are never edited.
If QQ changes during refresh, retry within a bounded budget and fail closed.
"""
import os
import json
import base64
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

SFDC = os.getenv("SFDC_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
MAX_ATTEMPTS = 3


def value(row, i):
    return str(row[i]).strip() if len(row) > i and row[i] is not None else ""


def project_rows(rows):
    """Match Sheets RAW string projection (21 columns) and trim right padding."""
    return [[value(row, i) for i in range(21)] for row in rows]


def nonempty_uid_rows(matrix):
    return [row for row in matrix[1:] if value(row, 8)]


def validate_source(triage, previous, ledger):
    if not triage or value(triage[0], 8) != "Thread UID":
        raise RuntimeError("Unexpected QQ triage columns; no writes performed")
    if not ledger or value(ledger[0], 4) != "Mail UID (Key)":
        raise RuntimeError("Unexpected SFDC decision columns; no writes performed")
    if not previous or value(previous[0], 8) != "Thread UID":
        raise RuntimeError("Unexpected SFDC snapshot columns; no writes performed")
    if project_rows([triage[0]]) != project_rows([previous[0]]):
        raise RuntimeError("QQ/SFDC mail columns differ; no writes performed")
    items = nonempty_uid_rows(triage)
    previous_items = nonempty_uid_rows(previous)
    if not items and previous_items:
        raise RuntimeError("QQ triage unexpectedly empty; preserving SFDC data")
    if not items:
        raise RuntimeError("QQ triage has zero mail rows; refusing PASS")
    if len(items) > 999:
        raise RuntimeError("SFDC snapshot limit exceeded; refusing truncation")
    uids = [value(r, 8) for r in items]
    if len(uids) != len(set(uids)):
        raise RuntimeError("Duplicate QQ thread UIDs; preserving SFDC data")
    return items, previous_items, uids


def main():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Google credential is missing")
    try:
        key = json.loads(raw)
    except ValueError:
        key = json.loads(base64.b64decode(raw))
    api = build("sheets", "v4", credentials=service_account.Credentials.from_service_account_info(
        key, scopes=["https://www.googleapis.com/auth/spreadsheets"]),
        cache_discovery=False).spreadsheets().values()

    def read(book, tab, area):
        return api.get(spreadsheetId=book, range="'"+tab+"'!"+area,
                       valueRenderOption="FORMATTED_VALUE").execute().get("values", [])

    dry = os.getenv("DRY_RUN", "true").lower() != "false"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        triage = read(QQ, "BI Unanswered Triage", "A1:U1200")
        ledger = read(SFDC, "Email Review Decisions", "A1:J1300")
        previous = read(SFDC, "Unanswered Emails", "A1:U1000")
        items, previous_items, uids = validate_source(triage, previous, ledger)
        existing = {value(r, 4) for r in ledger[1:] if value(r, 4)}
        new = []
        for r in items:
            uid = value(r, 8)
            if uid in existing:
                continue
            existing.add(uid)
            new.append(["NONE", value(r, 2), value(r, 4), value(r, 0), uid,
                        value(r, 16), "", "NOT_SUBMITTED", "", value(r, 3)])
        if len(ledger) - 1 + len(new) > 1299:
            raise RuntimeError("SFDC decision ledger capacity exceeded")
        print(json.dumps({"dry_run": dry, "attempt": attempt,
                          "qq_triage": len(items), "new_decisions": len(new)}))
        if dry:
            return

        # No rewrite of manually selected decisions: append only missing UIDs
        # as NONE. Reread the ledger on every retry to prevent duplicate appends.
        if new:
            start = len(ledger) + 1
            api.update(spreadsheetId=SFDC,
                       range="'Email Review Decisions'!A"+str(start),
                       valueInputOption="RAW", body={"values": new}).execute()

        # Replace only the 21-column read-only projection, never Decision cells.
        api.update(spreadsheetId=SFDC,
                   range="'Unanswered Emails'!A2",
                   valueInputOption="RAW",
                   body={"values": project_rows(items)}).execute()
        if len(previous_items) > len(items):
            first = len(items) + 2
            api.clear(spreadsheetId=SFDC,
                      range="'Unanswered Emails'!A"+str(first)+":U"+str(len(previous_items)+1),
                      body={}).execute()

        target = read(SFDC, "Unanswered Emails", "A1:U1000")
        live_source = read(QQ, "BI Unanswered Triage", "A1:U1200")
        if project_rows(nonempty_uid_rows(target)) == project_rows(nonempty_uid_rows(live_source)):
            # First confirm that the copy was exact, not merely equal in row
            # count or UID. A later source change will be caught at the next run.
            if project_rows(nonempty_uid_rows(target)) != project_rows(items):
                raise RuntimeError("Internal snapshot readback disagrees")
            print("SFDC_MAIL_SNAPSHOT_REFRESH=PASS READBACK_VERIFIED=true "+
                  "SOURCE_AND_TARGET_MATCH=true attempts="+str(attempt))
            return
        print("SFDC_MAIL_SNAPSHOT_SOURCE_CHANGED_RETRY="+str(attempt))

    raise RuntimeError("QQ triage changed during snapshot sync; no PASS recorded")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__+": "+str(exc), file=sys.stderr)
        sys.exit(1)
