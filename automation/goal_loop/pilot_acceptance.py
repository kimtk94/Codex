"""Independent pilot goal acceptance; run by local agent and its PR CI."""
import unittest

from automation.goal_loop.pilot_target import normalize_status


class PilotGoalAcceptance(unittest.TestCase):
    def test_known_success_aliases(self):
        for raw in (" pass ", "PASSED", "ok", "done", "success"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "PASS")

    def test_known_failure_aliases(self):
        for raw in ("failed", "FAIL", "error"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "FAIL")

    def test_unsupported_and_missing_is_hold(self):
        for raw in ("unknown", "", None, {}, 42):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "HOLD")


if __name__ == "__main__":
    unittest.main()
