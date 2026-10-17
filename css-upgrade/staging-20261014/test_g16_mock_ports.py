"""Strict mock-port regression; synthetic-only, no SSH or live services."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g16_mock_ports import DeniedOperation, PortBundle
from g16_synthetic_pipeline import FixtureEngine, IsolationError, SyntheticMail


class G16MockPortTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="g16-ports-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.messages = [
            SyntheticMail("test:m1", "synthetic:m1", "TEST-A", "SIF requested"),
            SyntheticMail("test:m2", None, "TEST-C", "Sample received", "SYN-201"),
            SyntheticMail("test:m3", "synthetic:m3", "TEST-C", "Sample received", "SYN-201"),
        ]
        self.ports = PortBundle(self.messages, {"TEST-A": "synthetic-inquiry"}, self.root)
        self.engine = FixtureEngine(self.root / "fixture.sqlite3", sqlite_factory=self.ports.sqlite)
        self.addCleanup(self.engine.close)
        self.engine.bootstrap([
            ("TEST-A", "SIF requested", True),
            ("TEST-B", "SIF requested", True),
            ("TEST-C", "Sample QC review", False),
        ])

    def run_fixture(self):
        return self.engine.run(self.ports.mail, self.ports.crm, self.ports.sheets)

    def test_001_strict_ports_use_synthetic_fixture(self):
        self.assertTrue(self.run_fixture())
        self.assertEqual(self.engine.counts(), (3, 2, 2))
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "auto_prepayment")
        self.assertIn(("TEST-A", "CRM_INQUIRY"), self.ports.sheets.actions)
        self.assertNotIn(("TEST-A", "SIF_FOLLOWUP"), self.ports.sheets.actions)
        self.assertEqual(self.ports.sheets.writes, 1)
        counters = self.ports.ledger.summary()
        self.assertGreater(counters.get("sqlite_execute", 0), 0)
        self.assertEqual(counters.get("sheets_publish"), 1)

    def test_002_idempotency_with_injected_ports(self):
        self.assertTrue(self.run_fixture())
        initial = self.engine.counts()
        self.assertFalse(self.run_fixture())
        self.assertEqual(self.engine.counts(), initial)
        self.assertEqual(self.ports.sheets.writes, 1)

    def test_003_manual_hold_not_replaced(self):
        self.engine.set_manual("TEST-A", "Hold")
        self.run_fixture()
        self.assertEqual(self.engine.snooze_mode("TEST-A"), "Hold")

    def test_004_qc_releases_only_auto_snooze(self):
        self.engine.set_manual("TEST-B", "Skip")
        self.run_fixture()
        self.engine.set_stage("TEST-A", "Sample QC review")
        self.run_fixture()
        self.assertIsNone(self.engine.snooze_mode("TEST-A"))
        self.assertEqual(self.engine.snooze_mode("TEST-B"), "Skip")
        self.assertIn(("TEST-A", "QC_REVIEW"), self.ports.sheets.actions)

    def test_005_error_before_sheet_publish_rolls_back(self):
        self.run_fixture()
        counts_before = self.engine.counts()
        portfolio_before = self.ports.sheets.portfolio
        self.ports.sheets.fail_next_write()
        incoming = self.ports.mail
        incoming._mail.messages.append(
            SyntheticMail("test:new", "synthetic:new", "TEST-C", "Data ready")
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic-sheet-write-failed"):
            self.run_fixture()
        self.assertEqual(self.engine.counts(), counts_before)
        self.assertEqual(self.ports.sheets.portfolio, portfolio_before)

    def test_006_unknown_network_and_sheet_operations_denied(self):
        for obj, name in [
            (self.ports.mail, "sendmail"),
            (self.ports.crm, "query_salesforce"),
            (self.ports.sheets, "open_by_key"),
            (self.ports.sheets, "batch_update"),
            (self.ports.sqlite, "attach"),
            (self.ports.files, "upload"),
            (self.ports, "unknown_sink"),
        ]:
            with self.subTest(name=name), self.assertRaises(DeniedOperation):
                getattr(obj, name)

    def test_007_sql_external_attach_and_export_denied(self):
        for query in [
            "ATTACH DATABASE '/tmp/external.db' AS other",
            "VACUUM INTO '/tmp/export.sqlite3'",
            "SELECT 1; DELETE FROM projects",
            "DROP TABLE projects",
            "PRAGMA writable_schema=ON",
        ]:
            with self.subTest(query=query), self.assertRaises(DeniedOperation):
                self.engine.db.execute(query)

    def test_008_sql_cursor_exec_denied(self):
        cur = self.engine.db.execute("SELECT COUNT(*) FROM projects")
        self.assertEqual(cur.fetchone()[0], 3)
        with self.assertRaises(DeniedOperation):
            cur.execute("DELETE FROM projects")

    def test_009_synthetic_sheet_rejects_production_row(self):
        with self.assertRaises(DeniedOperation):
            self.ports.sheets.publish((("AMEA2026100001", "SIF requested"),), ())
        with self.assertRaises(DeniedOperation):
            self.ports.sheets.publish((), (("AMEA2026100001", "FOLLOWUP"),))

    def test_010_fixture_files_metrics_only(self):
        self.ports.files.write_metrics("audit.json", {"count": 3, "healthy": True})
        self.assertEqual(
            json.loads((self.root / "audit.json").read_text()),
            {"count": 3, "healthy": True},
        )
        with self.assertRaises(DeniedOperation):
            self.ports.files.write_metrics("../export.json", {"count": 1})
        with self.assertRaises(DeniedOperation):
            self.ports.files.write_metrics("private.json", {"customer": "data"})
        with self.assertRaises(DeniedOperation):
            self.ports.files.write_metrics("unsafe.json", {"token": "secret"})

    def test_011_symlink_output_escape_denied(self):
        target = self.root / "audit.json"
        target.symlink_to("/etc/passwd")
        with self.assertRaises(DeniedOperation):
            self.ports.files.write_metrics("audit.json", {"count": 1})

    def test_012_sqlite_prod_path_denied(self):
        with self.assertRaises(IsolationError):
            self.ports.sqlite.connect(Path("/home/taehoon/services/novogene-css/data/prod.sqlite3"))

    def test_013_env_mode_required_every_call(self):
        with patch.dict(os.environ, {"G16_SYNTHETIC_ONLY": "0"}):
            with self.assertRaises(IsolationError):
                self.ports.mail.receive()
            with self.assertRaises(IsolationError):
                self.ports.crm.pending()
            with self.assertRaises(IsolationError):
                self.ports.files.write_metrics("audit.json", {"count": 1})

    def test_014_operation_ledger_is_aggregate_only(self):
        self.run_fixture()
        record = self.ports.ledger.summary()
        serialized = json.dumps(record)
        for token in ("TEST-A", "synthetic:m1", "SYN-201", "SELECT", "INSERT"):
            self.assertNotIn(token, serialized)
        self.assertTrue(all(isinstance(v, int) for v in record.values()))

    def test_015_missing_message_id_same_sample_dedup(self):
        self.run_fixture()
        self.assertEqual(self.engine.counts()[:2], (3, 2))

    def test_016_orphan_project_cannot_commit(self):
        self.ports.mail._mail.messages.append(
            SyntheticMail("test:bad", "synthetic:bad", "TEST-UNKNOWN", "Sample received")
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_fixture()
        self.assertEqual(self.engine.counts(), (0, 0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
