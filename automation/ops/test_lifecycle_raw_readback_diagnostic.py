#!/usr/bin/env python3
import unittest
from collections import Counter
from lifecycle_raw_readback_diagnostic import classify, mismatch_summary
from project_lifecycle_refresh import HEAD


class LifecycleRawDiagnosticTests(unittest.TestCase):
    def test_numeric_representation_only_is_not_loss(self):
        self.assertEqual(classify(97.0, 97, 7), "NUMERIC_REPRESENTATION_ONLY")
        self.assertEqual(classify("1.00", 1, 14), "NUMERIC_REPRESENTATION_ONLY")
        self.assertEqual(classify("1000000", 1000000.0, 15),
                         "NUMERIC_REPRESENTATION_ONLY")

    def test_text_date_and_identity_never_silently_coerced(self):
        self.assertEqual(classify("2026-11-18", "2026-11-17", 11),
                         "TRUE_VALUE_DIFFERENCE")
        self.assertEqual(classify("X0001", "X1", 0), "TRUE_VALUE_DIFFERENCE")
        self.assertEqual(classify("Statement ready", "Invoice issued", 16),
                         "TRUE_VALUE_DIFFERENCE")
        self.assertEqual(classify("", 0, 15), "BLANK_DIFFERENCE")

    def test_full_24_column_diff_counters_no_customer_data(self):
        expected = list(HEAD)
        a = [""] * 24
        a[0] = "XPRIVATE"
        a[7] = 100.0
        a[11] = "2026-11-18"
        b = list(a)
        b[7] = 100
        summary = mismatch_summary([expected, a], [expected, b])
        self.assertEqual(summary["NUMERIC_REPRESENTATION_ONLY"], 1)
        self.assertEqual(summary["TRUE_VALUE_DIFFERENCE"], 0)
        self.assertEqual(summary["ROWS_WITH_ANY_MISMATCH"], 1)
        self.assertNotIn("XPRIVATE", str(summary))

    def test_real_invoice_change_is_block(self):
        a, b = [""] * 24, [""] * 24
        a[0] = b[0] = "XPRIVATE"
        a[15], b[15] = 2000000, 1000000
        report = mismatch_summary([HEAD, a], [HEAD, b])
        self.assertEqual(report["TRUE_VALUE_DIFFERENCE"], 1)
        self.assertEqual(report["COLUMN_15_TRUE_VALUE_DIFFERENCE"], 1)

    def test_row_count_and_header_change_block(self):
        self.assertEqual(mismatch_summary([HEAD, ["X1"]], [HEAD])["ROW_COUNT_MATCH"], 0)
        self.assertEqual(mismatch_summary([HEAD], [["Wrong"]])["HEADER_EQUAL"], 0)


if __name__ == "__main__":
    unittest.main()
