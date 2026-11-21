#!/usr/bin/env python3
"""Deterministic fixtures only; no GitHub API or production credentials."""
import datetime as dt
import unittest
from project_quote_schedule_watchdog import classify, UTC

NOW = dt.datetime(2026, 11, 17, 0, 0, tzinfo=UTC)


def fixture(hours_ago, status="completed", conclusion="success", event="schedule"):
    stamp = NOW - dt.timedelta(hours=hours_ago)
    return {"event": event, "created_at": stamp.isoformat(),
            "status": status, "conclusion": conclusion}


class WatchdogTests(unittest.TestCase):
    def test_successful_recent_schedule_is_not_original_source_certification(self):
        r = classify({"workflow_runs": [fixture(1)]}, NOW)
        self.assertEqual(r["status"], "RECENT_SCHEDULE_SUCCESS")
        self.assertFalse(r["original_feishu_verified"])
        self.assertFalse(r["source_mirror_verified"])

    def test_missed_schedule_even_if_last_was_successful(self):
        r = classify({"workflow_runs": [fixture(9)]}, NOW)
        self.assertEqual(r["status"], "MISSED_SCHEDULE")
        self.assertEqual(r["last_schedule_conclusion"], "success")

    def test_dispatch_success_does_not_mask_missing_schedule(self):
        r = classify({"workflow_runs": [fixture(0.2, event="workflow_dispatch"),
                                         fixture(9)]}, NOW)
        self.assertEqual(r["status"], "MISSED_SCHEDULE")

    def test_latest_scheduled_failure_is_not_masked_by_older_success(self):
        r = classify({"workflow_runs": [fixture(1, conclusion="failure"),
                                         fixture(3)]}, NOW)
        self.assertEqual(r["status"], "LAST_SCHEDULE_FAILED")
        self.assertEqual(r["last_success_at_utc"],
                         fixture(3)["created_at"])

    def test_running_is_not_claimed_completed(self):
        r = classify({"workflow_runs": [fixture(1, "in_progress", None)]}, NOW)
        self.assertEqual(r["status"], "RUN_IN_PROGRESS")
        self.assertEqual(r["last_schedule_conclusion"], "NOT_FINISHED")

    def test_no_scheduled_runs(self):
        r = classify({"workflow_runs": [fixture(1, event="pull_request")]}, NOW)
        self.assertEqual(r["status"], "NO_SCHEDULED_RUN")

    def test_schema_or_future_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "WORKFLOW_RUN_SCHEMA"):
            classify({"other": []}, NOW)
        with self.assertRaisesRegex(ValueError, "SCHEDULE_TIMESTAMP_IN_FUTURE"):
            classify({"workflow_runs": [fixture(-1)]}, NOW)


if __name__ == "__main__":
    unittest.main()
