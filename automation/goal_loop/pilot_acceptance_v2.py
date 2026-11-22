"""Independent V2 acceptance; execute only in credential-free PR GitHub Actions."""
import unittest

from automation.goal_loop.pilot_target_v2 import normalize_status


class PilotV2Acceptance(unittest.TestCase):
    def test_success_aliases(self):
        for raw in ("pass", " PASSED ", "ok", "DONE", "Success", " PaSs "):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "PASS")

    def test_failure_aliases(self):
        for raw in ("fail", "Failed", " ERROR ", "fAiL"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "FAIL")

    def test_hold_and_nonstrings(self):
        for raw in ("UNKNOWN", "", " pending ", None, {}, 42, True, []):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(raw), "HOLD")


if __name__ == "__main__":
    unittest.main()
