"""Synthetic, credential-free regression for retired-server-to-V4 migration."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import css_modern_project_freshness as monitor


def example(status="PASS_MIRROR_ONLY"):
    return {
        "status": status,
        "source_count": 111,
        "sink_count": 111,
        "source_sink_mismatch_count": 0,
        "missing_project_count": 0,
        "unexpected_project_count": 0,
        "source_synced_at": "2026-11-16T15:57:42+09:00",
        "sink_generated_at": "2026-11-16T17:00:00+09:00",
        "checked_at": "2026-11-16T17:03:00+09:00",
        "mail_mirror_updated_at": "2026-11-16T16:20:07+09:00",
        "source_manifest_date": "2026-11-16",
        "original_feishu_verified": False,
        "original_qq_verified": False,
        "financial_actual_certified": False,
        "sfdc_save_verified": False,
        "project_rows": [
            {"project_id": "SYNTHETIC_001", "name": "PRIVATE_CUSTOMER_NAME"}
        ],
        "secret": "PRIVATE_API_TOKEN"
    }


class RetiredServerMigrationTests(unittest.TestCase):
    def test_pass_is_scoped_to_google_mirror_and_redacted(self):
        result = monitor.summarize(example())
        self.assertEqual("PASS_MIRROR_ONLY", result["status"])
        self.assertEqual("RETIRED_NOT_A_SOURCE", result["legacy_css_project_dashboard"])
        self.assertEqual("NOT_VERIFIED", result["business_source_sink_verification"])
        self.assertFalse(result["qq_original_source_verified"])
        self.assertFalse(result["feishu_original_source_verified"])
        self.assertNotIn("PRIVATE_CUSTOMER_NAME", str(result))
        self.assertNotIn("PRIVATE_API_TOKEN", str(result))
        self.assertNotIn("SYNTHETIC_001", str(result))

    def test_sink_mismatch_never_promoted_to_pass(self):
        item = example()
        item["missing_project_count"] = 1
        with self.assertRaisesRegex(ValueError, "FALSE_MIRROR_PARITY"):
            monitor.summarize(item)
        item["status"] = "SINK_LAG"
        self.assertEqual("SINK_LAG", monitor.summarize(item)["status"])

    def test_original_source_claim_is_never_accepted(self):
        for flag in ("original_feishu_verified", "original_qq_verified",
                     "sfdc_save_verified", "financial_actual_certified"):
            item = example()
            item[flag] = True
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(ValueError, "UNPROVEN"):
                    monitor.summarize(item)

    def test_incomplete_mail_window_and_stale_are_not_pass(self):
        for status in ("PARTIAL_MIRROR", "SINK_LAG", "STALE", "SOURCE_UNAVAILABLE"):
            with self.subTest(status=status):
                item = example(status)
                self.assertEqual(status, monitor.summarize(item)["status"])

    def test_never_accept_malformed_status_or_unbounded_counts(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN"):
            monitor.summarize({"status": "PASS"})
        for value in (-1, 100000, "111", True):
            item = example()
            item["source_count"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "MIRROR_ROW_COUNT"):
                    monitor.summarize(item)

    def test_main_without_credentials_never_emits_customers(self):
        with patch.object(monitor, "read_modern_mirror", return_value=example()):
            from contextlib import redirect_stdout
            import io
            capture = io.StringIO()
            with redirect_stdout(capture):
                exit_code = monitor.main()
            self.assertEqual(0, exit_code)
            self.assertNotIn("PRIVATE_CUSTOMER_NAME", capture.getvalue())
            self.assertNotIn("PRIVATE_API_TOKEN", capture.getvalue())

    def test_read_failure_is_fail_closed_without_error_details(self):
        from contextlib import redirect_stdout
        import io, json
        with patch.object(monitor, "read_modern_mirror",
                          side_effect=RuntimeError("PRIVATE_ERROR_AND_CLIENT_NAME")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = monitor.main()
        self.assertEqual(2, exit_code)
        result = json.loads(buf.getvalue())
        self.assertEqual("SOURCE_UNAVAILABLE", result["status"])
        self.assertNotIn("PRIVATE_ERROR", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
