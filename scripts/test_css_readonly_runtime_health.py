"""Synthetic-only, offline tests for CSS read-only runtime audit."""
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from css_readonly_runtime_health import (
    age_minutes, audit, interpret_runlog, inventory, parse_utc,
)

NOW = dt.datetime(2026, 10, 17, 10, 0, tzinfo=dt.timezone.utc)


def mail_payload():
    return {
        "total_candidates": 10,
        "processed_count": 10,
        "queued_count": 10,
        "sheet_saved_count": 10,
        "pending_count": 0,
        "failed_count": 0,
        "updated_at": "2026-10-17T09:51:00Z",
    }


def project_payload():
    return {"status": "SUCCESS", "run_at": "2026-10-17T09:45:00+00:00"}


class LogTests(unittest.TestCase):
    def test_recent_project(self):
        r = interpret_runlog(project_payload(), kind="project", now=NOW)
        self.assertEqual(r["status"], "SUCCESS")
        self.assertTrue(r["fresh"])

    def test_mail_consistent_is_not_claimed_explicit_success(self):
        r = interpret_runlog(mail_payload(), kind="mail", now=NOW)
        self.assertEqual(r["status"], "COUNTS_CONSISTENT_NOT_EXPLICIT_SUCCESS")
        self.assertTrue(r["fresh"])

    def test_failure_pending_partial_fail_closed(self):
        for field, value in (("failed_count", 1), ("pending_count", 1),
                             ("sheet_saved_count", 9), ("queued_count", 9),
                             ("processed_count", 9)):
            with self.subTest(field=field):
                payload = mail_payload()
                payload[field] = value
                r = interpret_runlog(payload, kind="mail", now=NOW)
                self.assertEqual(r["status"], "COUNTS_NEED_REVIEW")

    def test_missing_invalid_counters(self):
        for val in (None, -1, True, "10"):
            with self.subTest(val=val):
                payload = mail_payload()
                payload["queued_count"] = val
                self.assertEqual(interpret_runlog(payload, kind="mail", now=NOW)["status"],
                                 "MISSING_COUNTERS")

    def test_mail_stale_and_future(self):
        payload = mail_payload()
        payload["updated_at"] = "2026-10-17T08:00:00Z"
        self.assertEqual(interpret_runlog(payload, kind="mail", now=NOW)["status"],
                         "STALE_COUNTS_CONSISTENT")
        payload["updated_at"] = "2026-10-17T10:10:00Z"
        self.assertEqual(interpret_runlog(payload, kind="mail", now=NOW)["status"],
                         "INVALID_TIMESTAMP")

    def test_bad_and_naive_timestamps(self):
        self.assertIsNone(parse_utc("2026-10-17T10:00:00"))
        self.assertIsNone(parse_utc("garbage"))
        self.assertIsNone(age_minutes("2026-10-17T11:00:00Z", NOW))

    def test_project_stale_failed_unknown(self):
        p = project_payload()
        p["run_at"] = "2026-10-17T06:00:00Z"
        self.assertEqual(interpret_runlog(p, kind="project", now=NOW)["status"],
                         "STALE_SUCCESS")
        p["run_at"] = "2026-10-17T09:45:00Z"
        p["status"] = "FAILED"
        self.assertEqual(interpret_runlog(p, kind="project", now=NOW)["status"], "FAILED")
        p["status"] = "anything"
        self.assertEqual(interpret_runlog(p, kind="project", now=NOW)["status"], "UNKNOWN_STATUS")

    def test_non_dict_payload(self):
        self.assertEqual(interpret_runlog([], kind="mail", now=NOW)["status"], "UNVERIFIED")

    def test_end_to_end_temporary_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "logs").mkdir()
            for name in ("css_project_manager.sqlite3", "mail_sync_fast.sqlite3"):
                conn = sqlite3.connect(root / "state" / name)
                conn.execute("CREATE TABLE fixtures(id INTEGER PRIMARY KEY)")
                conn.commit()
                conn.close()
            (root / "logs" / "css_project_manager_run_log.json").write_text(
                json.dumps(project_payload()))
            (root / "logs" / "all_email_fast_run_log.json").write_text(
                json.dumps(mail_payload()))
            report = audit(root, now=NOW)
            self.assertEqual(report["runtime_indicators"], "CONSISTENT")
            self.assertFalse(report["mail_delivery_confirmed"])
            self.assertFalse(report["production_deploy_authorized"])
            self.assertEqual(report["databases"]["project_database"]["integrity"], "PASS")

    def test_ignore_backup_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backup").mkdir()
            (root / "state").mkdir()
            (root / "backup" / "mail_sync_fast.sqlite3").write_text("not a database")
            (root / "state" / "mail_sync_fast.sqlite3").symlink_to(
                root / "backup" / "mail_sync_fast.sqlite3")
            result = inventory(root)
            self.assertEqual(result["mail_sync_fast.sqlite3"], [])

    def test_empty_inventory_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = audit(Path(tmp), now=NOW)
            self.assertEqual(report["runtime_indicators"], "NEEDS_REVIEW")
            self.assertEqual(report["databases"]["project_database"]["integrity"], "NOT_FOUND")

    def test_no_customer_details_echoed(self):
        p = mail_payload()
        p["customer_email"] = "private@example.invalid"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "all_email_fast_run_log.json").write_text(json.dumps(p))
            result = audit(root, now=NOW)
            self.assertNotIn("private@example.invalid", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
