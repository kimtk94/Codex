"""Credential-free tests of local SQLite-only invoice replay semantics."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from automation.css_mail.qq_replay_transaction_rehearsal import (
    demo, init_demo, rehearse,
)


def case(num="209126000001", amount="5000"):
    return {"invoice_number": num, "amount_krw": amount,
            "imap_uid": "321", "uidvalidity": "1234", "issued_month": ""}


class ReplayRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", timeout=0)
        init_demo(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_missing_approval_never_inserts(self):
        self.assertEqual(rehearse(self.conn, case()), "APPROVAL_ABSENT_HOLD")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM staged_invoice").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM receipt").fetchone()[0], 0)

    def test_simulated_success_then_same_id_is_noop(self):
        c = case()
        self.assertEqual(rehearse(self.conn, c, synthetic_approval=True),
                         "SIMULATED_LOCAL_WRITE_VERIFIED")
        self.assertEqual(rehearse(self.conn, c, synthetic_approval=True),
                         "SIMULATED_ALREADY_VERIFIED_NOOP")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM staged_invoice").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT result FROM receipt").fetchone()[0], "VERIFIED")

    def test_crash_between_append_and_receipt_remains_hold(self):
        c = case()
        self.assertEqual(rehearse(self.conn, c, synthetic_approval=True,
                                 crash_after_append=True),
                         "SIMULATED_CRASH_UNCERTAIN_HOLD")
        self.assertEqual(rehearse(self.conn, c, synthetic_approval=True),
                         "UNCERTAIN_OR_CONFLICT_HOLD")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM staged_invoice").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT result FROM receipt").fetchone()[0], "UNCERTAIN")

    def test_altered_amount_cannot_overwrite_verified_row(self):
        self.assertEqual(rehearse(self.conn, case(), synthetic_approval=True),
                         "SIMULATED_LOCAL_WRITE_VERIFIED")
        self.assertEqual(rehearse(self.conn, case(amount="6000"), synthetic_approval=True),
                         "UNCERTAIN_OR_CONFLICT_HOLD")
        self.assertEqual(self.conn.execute("SELECT amount_krw FROM staged_invoice").fetchone()[0],
                         "5000")

    def test_unjournaled_existing_row_is_not_rewritten(self):
        c = case()
        self.conn.execute("INSERT INTO staged_invoice VALUES (?,?,?,?,?)", tuple(c.values()))
        self.conn.commit()
        self.assertEqual(rehearse(self.conn, c, synthetic_approval=True),
                         "EXISTING_UNJOURNALED_ROW_HOLD")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM receipt").fetchone()[0], 0)

    def test_simulated_second_connection_cannot_break_reserved_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / "synthetic.sqlite3")
            a = sqlite3.connect(filename, timeout=0)
            b = sqlite3.connect(filename, timeout=0)
            try:
                init_demo(a)
                a.execute("BEGIN IMMEDIATE")
                self.assertEqual(rehearse(b, case(), synthetic_approval=True),
                                 "SIMULATED_DB_ERROR_HOLD")
                a.rollback()
                self.assertEqual(rehearse(b, case(), synthetic_approval=True),
                                 "SIMULATED_LOCAL_WRITE_VERIFIED")
            finally:
                a.close()
                b.close()

    def test_month_and_identity_restrictions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "SIMULATION_CASE_VALUES_INVALID"):
            rehearse(self.conn, case() | {"issued_month": "2026-11"},
                     synthetic_approval=True)
        with self.assertRaisesRegex(ValueError, "SIMULATION_CASE_VALUES_INVALID"):
            rehearse(self.conn, case(amount="0"), synthetic_approval=True)

    def test_demo_counts_never_claim_real_authority_or_print_invoice(self):
        result = demo()
        self.assertEqual(result["synthetic_case_count"], 7)
        self.assertEqual(result["simulated_first_insert_verified"], 7)
        self.assertEqual(result["simulated_idempotent_noop"], 7)
        for key in ("google_sheets_writes", "cursor_writes", "canonical_writes",
                    "real_approvals_verified", "cross_writer_lock_verified",
                    "real_receipts_verified"):
            self.assertEqual(result[key], 0)
        self.assertEqual(result["production_status"], "HOLD")
        self.assertNotIn("209126", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
