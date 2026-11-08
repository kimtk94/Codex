#!/usr/bin/env python3
"""Fail closed when the scheduled SFDC 3-report source is not actually current.

A successful GitHub job, a recent *ingest check*, or reusing the last good
Google Sheet is not evidence that the latest QQ Salesforce report arrived.
Read only the 3-report audit header/timestamps. Never read customer contents.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
REQUIRED = ("Leads", "Opportunities", "Quotation")
HEADER = ("Entity", "Source Received KST", "Ingest Checked KST", "Rows",
          "Unique IDs", "Duplicate IDs", "Missing IDs", "Content SHA256",
          "State", "Source Kind")
VALID_STATES = {"STAGED_NOT_PROMOTED", "PRESERVED_NO_NEW_REPORT"}
SLOTS = (9, 12, 17)


def parse_kst(value):
    if not isinstance(value, str) or not value.endswith(" KST"):
        raise ValueError("SOURCE_TIMESTAMP_INVALID")
    try:
        stamp = dt.datetime.strptime(value[:-4], "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("SOURCE_TIMESTAMP_INVALID") from exc
    return stamp.replace(tzinfo=KST)


def latest_due(now, grace_minutes=35):
    """Expected 09/12/17 KST subscription, including previous day overnight."""
    if now.tzinfo is None:
        raise ValueError("NOW_MUST_BE_AWARE")
    local = now.astimezone(KST)
    for offset in (0, 1):
        day = local.date() - dt.timedelta(days=offset)
        for hour in reversed(SLOTS):
            slot = dt.datetime.combine(day, dt.time(hour, 0), tzinfo=KST)
            if local >= slot + dt.timedelta(minutes=grace_minutes):
                return slot
    raise AssertionError("NO_SOURCE_SLOT")


def inspect(rows, now, grace_minutes=35):
    """Return evidence with stale entities; never confuse checked_at and received_at."""
    if not rows or tuple(rows[0][:10]) != HEADER:
        raise ValueError("AUDIT_SCHEMA_MISMATCH")
    due = latest_due(now, grace_minutes=grace_minutes)
    local = now.astimezone(KST)
    by_entity = {}
    for row in rows[1:]:
        if not row or row[0] not in REQUIRED:
            continue
        if row[0] in by_entity or len(row) < 10:
            raise ValueError("AUDIT_ENTITY_DUPLICATE_OR_TRUNCATED")
        by_entity[row[0]] = row
    if set(by_entity) != set(REQUIRED):
        raise ValueError("AUDIT_ENTITIES_INCOMPLETE")
    stale = []
    received = {}
    checked = {}
    for name in REQUIRED:
        row = by_entity[name]
        if row[8] not in VALID_STATES or row[9] != "QQ IMAP":
            raise ValueError("UNTRUSTED_AUDIT_RECORD")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", row[7]):
            raise ValueError("AUDIT_HASH_INVALID")
        if not row[3].isdigit() or not row[4].isdigit() or row[6] != "0":
            raise ValueError("AUDIT_COVERAGE_INVALID")
        if int(row[3]) < 1 or int(row[4]) < 1:
            raise ValueError("AUDIT_COVERAGE_EMPTY")
        original = parse_kst(row[1])
        audit_check = parse_kst(row[2])
        if original > local + dt.timedelta(minutes=10) or audit_check > local + dt.timedelta(minutes=10):
            raise ValueError("AUDIT_TIMESTAMP_IN_FUTURE")
        received[name] = original
        checked[name] = audit_check
        # Salesforce subscription mail is observed around 08:00 KST on
        # 2026-11-08 even though the canonical morning due slot is 09:00.
        # A delivered 08:00 report is still *today's morning* snapshot.
        # Allow at most 75 minutes early (09:00 -> 07:45), without accepting
        # yesterday's 17:00 source or an old morning source after the 12:00
        # and 17:00 due slots. The received header, not the check time,
        # remains the authoritative freshness evidence.
        if original < due - dt.timedelta(minutes=75):
            stale.append(name)
    return {"due": due, "stale": stale, "received": received, "checked": checked}


def main():
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("READONLY_SOURCE_AUTH_MISSING")
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    auth = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    cell = urllib.parse.quote("'SFDC Email Ingest Audit'!A1:J10", safe="")
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + "/values/" + cell
    resp = AuthorizedSession(auth).get(url, timeout=45)
    resp.raise_for_status()
    state = inspect(resp.json().get("values", []), dt.datetime.now(KST))
    due = state["due"].strftime("%Y-%m-%d %H:%M KST")
    # Aggregates only: no customer IDs, names, mail subjects, credentials or amounts.
    for entity in REQUIRED:
        print("SFDC_SOURCE_EVIDENCE entity=" + entity +
              " received=" + state["received"][entity].strftime("%Y-%m-%d %H:%M KST") +
              " checked=" + state["checked"][entity].strftime("%Y-%m-%d %H:%M KST"))
    if state["stale"]:
        print("::error title=SFDC reports stale::Expected latest " + due +
              "; missing slot=" + ",".join(state["stale"]))
        print("SFDC_FRESHNESS_RESULT=STALE due=" + due +
              " entities=" + ",".join(state["stale"]))
        raise RuntimeError("SFDC_REPORTS_NOT_CURRENT")
    print("SFDC_FRESHNESS_RESULT=PASS due=" + due + " entities=3")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("SFDC_FRESHNESS_GATE_FAILED=" + type(exc).__name__ + ":" +
              (str(exc) if isinstance(exc, ValueError) else "SOURCE_NOT_CURRENT"),
              file=sys.stderr)
        sys.exit(1)
