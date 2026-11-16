#!/usr/bin/env python3
"""No API, no customer data and no secrets."""
import datetime as dt
import unittest

from quote_header_source_health import assess, KST

NOW = dt.datetime(2026, 11, 17, 8, 0, tzinfo=KST)


def matrix(value, count=20):
    return [["Exported At KST"]] + [[value] for _ in range(count)]


class QuoteHeaderHealthTests(unittest.TestCase):
    def test_recent_uniform_header_is_mirror_only(self):
        value = "2026-11-17 02:00:00 KST"
        result = assess(matrix(value), NOW)
        self.assertEqual(result["status"], "HEADER_MIRROR_RECENT")
        self.assertFalse(result["original_sfdc_verified"])
        self.assertEqual(result["row_count"], 20)

    def test_october_header_is_stale_despite_new_process_report(self):
        result = assess(matrix("2026-10-24 18:00:08 KST", 814), NOW)
        self.assertEqual(result["status"], "STALE_QUOTE_HEADER")
        self.assertGreater(result["age_hours"], 72)
        self.assertEqual(result["row_count"], 814)

    def test_mixed_export_stamps_cannot_be_marked_recent(self):
        values = matrix("2026-11-17 02:00:00 KST")
        values[-1] = ["2026-10-24 18:00:08 KST"]
        self.assertEqual(assess(values, NOW)["status"], "MIXED_EXPORT_TIMESTAMPS")

    def test_missing_header_and_empty_or_tiny_column(self):
        with self.assertRaisesRegex(ValueError, "QUOTE_HEADER_COLUMN_MISMATCH"):
            assess([["Wrong field"], ["2026-11-17 02:00:00 KST"]], NOW)
        self.assertEqual(assess(matrix("2026-11-17 02:00:00 KST", 2), NOW)["status"],
                         "HEADER_MISSING_OR_TOO_SMALL")

    def test_malformed_or_future_export_is_not_current(self):
        values = matrix("2026-11-17 09:00:00 KST")
        self.assertEqual(assess(values, NOW)["status"], "FUTURE_EXPORT_TIMESTAMP")
        with self.assertRaisesRegex(ValueError, "INVALID_QUOTE_HEADER_TIMESTAMP"):
            assess(matrix("Nov 17 2026"), NOW)

    def test_naive_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "AWARE_CLOCK_REQUIRED"):
            assess(matrix("2026-11-17 02:00:00 KST"), dt.datetime(2026, 11, 17, 8))


if __name__ == "__main__":
    unittest.main()
