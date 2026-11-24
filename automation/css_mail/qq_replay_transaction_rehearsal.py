#!/usr/bin/env python3
"""Synthetic-only QQ stage replay transaction rehearsal.

This module operates exclusively on caller-provided SQLite connections. It
contains no Sheets, QQ mail, OAuth, HTTP or production writer adapter. A
synthetic approval bool is NEVER valid authority for actual financial writes.
SQLite locking does not protect the real Google Sheets staging tab.
"""
from collections import Counter
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS staged_invoice(
    invoice_number TEXT PRIMARY KEY,
    amount_krw TEXT NOT NULL,
    imap_uid TEXT NOT NULL,
    uidvalidity TEXT NOT NULL,
    issued_month TEXT NOT NULL CHECK(issued_month = '')
);
CREATE TABLE IF NOT EXISTS receipt(
    invoice_number TEXT PRIMARY KEY,
    result TEXT NOT NULL CHECK(result IN ('UNCERTAIN','VERIFIED'))
);
"""


def init_demo(conn):
    """Build a disposable local test schema. Never calls a remote service."""
    conn.executescript(SCHEMA)


def _row(case):
    fields = ("invoice_number", "amount_krw", "imap_uid",
              "uidvalidity", "issued_month")
    if not isinstance(case, dict) or set(case) != set(fields):
        raise ValueError("SIMULATION_CASE_SCHEMA_INVALID")
    values = tuple(str(case[k]) for k in fields)
    if not (values[0].isdigit() and 10 <= len(values[0]) <= 15
            and values[1].isdigit() and int(values[1]) > 0
            and values[2].isdigit() and values[3].isdigit()
            and values[4] == ""):
        raise ValueError("SIMULATION_CASE_VALUES_INVALID")
    return values


def rehearse(conn, case, synthetic_approval=False, crash_after_append=False):
    """Local-only idempotency and uncertain-result drill; NO PRODUCTION WRITE.

    Stage row and UNCERTAIN journal entry are committed together. A simulated
    crash happens before the *separate* verified receipt. Unknown outcomes must
    be reviewed rather than automatically retried.
    """
    expected = _row(case)
    if synthetic_approval is not True:
        return "APPROVAL_ABSENT_HOLD"
    try:
        conn.execute("BEGIN IMMEDIATE")
        receipt = conn.execute(
            "SELECT result FROM receipt WHERE invoice_number=?", (expected[0],)
        ).fetchone()
        existing = conn.execute(
            "SELECT invoice_number,amount_krw,imap_uid,uidvalidity,issued_month "
            "FROM staged_invoice WHERE invoice_number=?", (expected[0],)
        ).fetchone()
        if receipt:
            conn.rollback()
            if receipt[0] == "VERIFIED" and existing == expected:
                return "SIMULATED_ALREADY_VERIFIED_NOOP"
            return "UNCERTAIN_OR_CONFLICT_HOLD"
        if existing:
            conn.rollback()
            return "EXISTING_UNJOURNALED_ROW_HOLD"
        conn.execute(
            "INSERT INTO receipt(invoice_number,result) VALUES (?, 'UNCERTAIN')",
            (expected[0],))
        conn.execute(
            "INSERT INTO staged_invoice"
            "(invoice_number,amount_krw,imap_uid,uidvalidity,issued_month)"
            " VALUES (?,?,?,?,?)", expected)
        conn.commit()
        if crash_after_append:
            return "SIMULATED_CRASH_UNCERTAIN_HOLD"
        conn.execute("BEGIN IMMEDIATE")
        stored = conn.execute(
            "SELECT invoice_number,amount_krw,imap_uid,uidvalidity,issued_month "
            "FROM staged_invoice WHERE invoice_number=?", (expected[0],)
        ).fetchone()
        if stored != expected:
            conn.rollback()
            return "SIMULATED_READBACK_MISMATCH_HOLD"
        conn.execute("UPDATE receipt SET result='VERIFIED' "
                     "WHERE invoice_number=? AND result='UNCERTAIN'",
                     (expected[0],))
        conn.commit()
        return "SIMULATED_LOCAL_WRITE_VERIFIED"
    except sqlite3.Error:
        if conn.in_transaction:
            conn.rollback()
        return "SIMULATED_DB_ERROR_HOLD"


def demo():
    """Seven *synthetic* cases; zero credentials, zero remote writes."""
    con = sqlite3.connect(":memory:")
    init_demo(con)
    counts = Counter()
    for n in range(1, 8):
        case = {"invoice_number": f"{n:012d}", "amount_krw": "1000",
                "imap_uid": str(n + 100), "uidvalidity": "1234",
                "issued_month": ""}
        counts[rehearse(con, case, synthetic_approval=True)] += 1
        counts[rehearse(con, case, synthetic_approval=True)] += 1
    con.close()
    return {
        "status": "LOCAL_SIMULATION_ONLY",
        "synthetic_case_count": 7,
        "simulated_first_insert_verified": counts["SIMULATED_LOCAL_WRITE_VERIFIED"],
        "simulated_idempotent_noop": counts["SIMULATED_ALREADY_VERIFIED_NOOP"],
        "google_sheets_writes": 0,
        "cursor_writes": 0,
        "canonical_writes": 0,
        "real_approvals_verified": 0,
        "cross_writer_lock_verified": 0,
        "real_receipts_verified": 0,
        "production_status": "HOLD",
    }


if __name__ == "__main__":
    print("QQ_REPLAY_TRANSACTION_REHEARSAL=" + json.dumps(demo(), sort_keys=True))
