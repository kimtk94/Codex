"""The hosted audit must contain no user data, tokens, Drive content or false PASS."""
import json
import unittest
from unittest.mock import patch

from local_ai.ci.health_report import build_report


class HealthReportTests(unittest.TestCase):
    def test_report_declares_unverified_sources(self):
        report = build_report({"unit_tests": {"status": "PASS", "count": 9}}, 0)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["real_world_not_verified"]["windows_google_drive_desktop_sync"], "PENDING")
        self.assertEqual(report["real_world_not_verified"]["local_3b_codex_tool_use"], "HOLD")
        self.assertEqual(report["execution"]["drive_credentials"], "NOT_USED")
        self.assertEqual(report["execution"]["real_model_inference"], "NOT_RUN")

    def test_failure_is_not_reported_as_pass(self):
        report = build_report({"unit_tests": {"status": "FAIL", "count": None}}, 1)
        self.assertEqual(report["overall"], "FAIL")

    @patch.dict("os.environ", {
        "GITHUB_SHA": "f" * 40,
        "GITHUB_EVENT_NAME": "pull_request",
        "SECRET_TOKEN": "DO_NOT_EXPOSE_ME",
        "GOOGLE_DRIVE_SECRET": "DRIVE_CREDENTIAL_SECRET",
    })
    def test_sanitized_evidence_does_not_include_secrets(self):
        report = build_report({}, 0)
        serialized = json.dumps(report)
        self.assertEqual(report["source_sha"], "f" * 40)
        self.assertNotIn("DO_NOT_EXPOSE_ME", serialized)
        self.assertNotIn("DRIVE_CREDENTIAL_SECRET", serialized)
        self.assertEqual(report["event"], "pull_request")

    @patch.dict("os.environ", {"GITHUB_SHA": "attacker controlled value", "GITHUB_EVENT_NAME": "unknown"})
    def test_invalid_event_and_sha_are_not_copied(self):
        report = build_report({}, 1)
        self.assertEqual(report["source_sha"], "NOT_AVAILABLE")
        self.assertEqual(report["event"], "LOCAL")


if __name__ == "__main__":
    unittest.main()
