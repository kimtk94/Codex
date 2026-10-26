import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nba_schedule_health import KST, assess, expected_slot


class ScheduleHealthTests(unittest.TestCase):
    def test_wait_before_grace_period(self):
        now = dt.datetime(2026, 10, 27, 8, 30, tzinfo=KST)
        self.assertEqual(expected_slot(now), dt.datetime(2026, 10, 26, 17, tzinfo=KST))

    def test_expected_slot_after_grace(self):
        self.assertEqual(expected_slot(dt.datetime(2026, 10, 27, 9, 41, tzinfo=KST)),
                         dt.datetime(2026, 10, 27, 8, tzinfo=KST))

    def test_push_success_does_not_replace_schedule(self):
        slot = dt.datetime(2026, 10, 27, 8, tzinfo=KST)
        push = {"event": "push", "created_at": "2026-10-26T23:01:00Z",
                "status": "completed", "conclusion": "success"}
        self.assertEqual(assess(slot, [push])[0], "MISSING")

    def test_scheduled_success_and_failure(self):
        slot = dt.datetime(2026, 10, 27, 8, tzinfo=KST)
        run = {"event": "schedule", "created_at": "2026-10-26T23:05:00Z",
               "status": "completed", "conclusion": "success"}
        self.assertEqual(assess(slot, [run])[0], "SUCCESS")
        run["conclusion"] = "failure"
        self.assertEqual(assess(slot, [run])[0], "FAILED")


if __name__ == "__main__":
    unittest.main()
