"""Deterministic G16 fixture pipeline tests: no server access and no production code."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g16_synthetic_pipeline import (
    FakeCRM, FakeMail, FakeSheets, FixtureEngine,
    IsolationError, SyntheticMail,
)


class SyntheticPipelineTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="g16-fixture-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.engine = FixtureEngine(Path(self.tmp.name) / "fixture.sqlite3")
        self.addCleanup(self.engine.close)
        self.engine.bootstrap([
            ("TEST-A", "SIF requested", True),
            ("TEST-B", "SIF requested", True),
            ("TEST-C", "Sample QC review", False),
        ])
        self.sheet = FakeSheets()
        self.crm = FakeCRM({"TEST-A": "synthetic-inquiry"})
        self.mails = FakeMail([
            SyntheticMail("test:1", "synthetic:one", "TEST-A", "SIF requested"),
            SyntheticMail("test:2", "synthetic:sample-1", "TEST-C", "Sample received", "SYN-001"),
            SyntheticMail("test:3", "synthetic:sample-2", "TEST-C", "Sample received", "SYN-001"),
        ])

    def test_001_first_run_portfolio_and_actions(self):
        self.assertTrue(self.engine.run(self.mails, self.crm, self.sheet))
        self.assertEqual(self.engine.counts(), (3, 2, 2))
        self.assertEqual(self.sheet.writes, 1)
        self.assertEqual(len(self.sheet.portfolio), 3)
        self.assertIn(("TEST-A", "CRM_INQUIRY"), self.sheet.actions)
        self.assertIn(("TEST-C", "QC_REVIEW"), self.sheet.actions)
        self.assertNotIn(("TEST-A", "SIF_FOLLOWUP"), self.sheet.actions)
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "auto_prepayment")

    def test_002_identical_repeat_idempotency(self):
        self.assertTrue(self.engine.run(self.mails, self.crm, self.sheet))
        state = self.engine.counts()
        self.assertFalse(self.engine.run(self.mails, self.crm, self.sheet))
        self.assertEqual(self.engine.counts(), state)
        self.assertEqual(self.sheet.writes, 1)

    def test_003_manual_hold_survives_auto_snooze(self):
        self.engine.set_manual("TEST-A", "Hold")
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "Hold")
        self.assertNotIn(("TEST-A", "SIF_FOLLOWUP"), self.sheet.actions)

    def test_004_manual_skip_survives_auto_snooze(self):
        self.engine.set_manual("TEST-B", "Skip")
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertEqual(self.engine.snooze_mode("TEST-B"), "Skip")

    def test_005_qc_transition_releases_automatic_only(self):
        self.engine.run(self.mails, self.crm, self.sheet)
        self.engine.set_stage("TEST-A", "Sample QC review")
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertIsNone(self.engine.snooze_mode("TEST-A"))
        self.assertIn(("TEST-A", "QC_REVIEW"), self.sheet.actions)
        self.assertIn(("TEST-A", "CRM_INQUIRY"), self.sheet.actions)

    def test_006_manual_hold_survives_qc(self):
        self.engine.set_manual("TEST-A", "Hold")
        self.engine.set_stage("TEST-A", "Sample QC review")
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "Hold")
        self.assertNotIn(("TEST-A", "QC_REVIEW"), self.sheet.actions)

    def test_007_manual_release_and_rearm(self):
        self.engine.set_manual("TEST-A", "Hold")
        self.engine.set_manual("TEST-A", "Release")
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "auto_prepayment")

    def test_008_distinct_uid_same_sample_event_dedup(self):
        self.engine.run(self.mails, self.crm, self.sheet)
        self.assertEqual(self.engine.counts()[:2], (3, 2))

    def test_009_missing_message_id_still_deduplicates_sample(self):
        fixture = FakeMail([
            SyntheticMail("test:4", None, "TEST-C", "Sample received", "SYN-002"),
            SyntheticMail("test:5", None, "TEST-C", "Sample received", "SYN-002"),
        ])
        self.engine.run(fixture, self.crm, self.sheet)
        self.assertEqual(self.engine.counts()[:2], (2, 1))

    def test_010_failure_before_sheet_write_rolls_back_sqlite(self):
        self.engine.run(self.mails, self.crm, self.sheet)
        prior = self.engine.counts()
        old_rows = self.sheet.portfolio
        self.sheet.fail_next = True
        incoming = FakeMail([
            SyntheticMail("test:unexpected", "synthetic:new", "TEST-C", "Data ready")
        ])
        with self.assertRaisesRegex(RuntimeError, "synthetic-sheet-write-failed"):
            self.engine.run(incoming, self.crm, self.sheet)
        self.assertEqual(self.engine.counts(), prior)
        self.assertEqual(self.sheet.portfolio, old_rows)

    def test_011_unknown_project_rejects_orphan_timeline(self):
        incoming = FakeMail([
            SyntheticMail("test:unknown", "synthetic:unknown", "TEST-UNKNOWN", "Sample received")
        ])
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.run(incoming, self.crm, self.sheet)
        self.assertEqual(self.engine.counts(), (0, 0, 0))

    def test_012_production_identifiers_rejected(self):
        with self.assertRaises(IsolationError):
            FakeMail([SyntheticMail("inbox:1", "real@example.com", "AMEA2026100000", "SIF requested")])
        with self.assertRaises(IsolationError):
            FakeCRM({"AMEA2026100000": "any"})

    def test_013_outside_temp_database_denied(self):
        with self.assertRaises(IsolationError):
            FixtureEngine(Path("/var/tmp/css-production-like.sqlite3"))

    def test_014_explicit_synthetic_mode_required(self):
        with patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "0"}):
            with self.assertRaises(IsolationError):
                self.engine.run(self.mails, self.crm, self.sheet)


    def test_015_conflicting_mail_uid_fails_closed(self):
        self.engine.run(self.mails, self.crm, self.sheet)
        initial = self.engine.counts()
        incoming = FakeMail([
            SyntheticMail("test:1", "synthetic:conflict", "TEST-A", "Data ready")
        ])
        with self.assertRaisesRegex(IsolationError, "conflicting reuse"):
            self.engine.run(incoming, self.crm, self.sheet)
        self.assertEqual(self.engine.counts(), initial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
