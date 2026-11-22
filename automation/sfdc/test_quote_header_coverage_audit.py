#!/usr/bin/env python3
"""Deterministic source-gap cases, no network or customer identifiers."""
import unittest
from quote_header_coverage_audit import compare, exact_qid_index


def columns(*triples):
    return [[row[i] for row in triples] for i in range(3)]


class HeaderCoverageTests(unittest.TestCase):
    def test_new_and_old_qids_are_review_only(self):
        raw = columns(
            ("QID-2026-11-01-A", "OPP-A", "TRUE"),
            ("QID-2026-11-01-A", "OPP-A", "TRUE"),
            ("QID-2026-11-01-B", "OPP-B", "1"),
            ("QID-2026-11-01-C", "OPP-C", "0"),
            ("QID-2026-11-01-D", "OPP-D", "1"))
        old = columns(
            ("QID-2026-11-01-A", "OPP-A", "1"),
            ("QID-2026-11-01-B", "OPP-B", "TRUE"),
            ("QID-2026-11-01-C", "OPP-C", "1"),
            ("QID-2026-10-20-E", "OPP-E", "TRUE"))
        result = compare(raw, old)
        self.assertEqual(result["status"], "REVIEW_QUEUE")
        self.assertEqual((result["process_qids"], result["header_qids"]), (4, 4))
        self.assertEqual(result["overlap_qids"], 3)
        self.assertEqual(result["process_only_qids"], 1)
        self.assertEqual(result["header_only_qids"], 1)
        self.assertEqual(result["exact_qid_opportunity_active"], 2)
        self.assertEqual(result["active_mismatch"], 1)
        self.assertEqual(result["opportunity_mismatch"], 0)
        self.assertFalse(result["quote_name_verified"])
        self.assertFalse(result["quote_price_verified"])
        self.assertFalse(result["quote_sfdc_record_id_verified_for_new_only"])
        self.assertEqual(result["sfdc_writes"], 0)

    def test_opportunity_mismatch_is_never_auto_merged(self):
        x = columns(("QID-2026-11-01-A", "OPP-A", "1"))
        y = columns(("QID-2026-11-01-A", "OPP-OTHER", "1"))
        result = compare(x, y)
        self.assertEqual(result["opportunity_mismatch"], 1)
        self.assertEqual(result["exact_qid_opportunity_active"], 0)

    def test_ambiguous_source_is_not_exact(self):
        x = columns(("QID-2026-11-01-A", "OPP-A", "1"),
                    ("QID-2026-11-01-A", "OPP-B", "1"))
        y = columns(("QID-2026-11-01-A", "OPP-A", "1"))
        result = compare(x, y)
        self.assertEqual(result["ambiguous_or_missing_evidence"], 1)
        self.assertEqual(result["exact_qid_opportunity_active"], 0)

    def test_invalid_identifier_and_empty_active_are_not_passed(self):
        x = columns(("NOT_A_QID", "OPP-A", "1"),
                    ("QID-2026-11-01-A", "OPP-A", ""))
        y = columns(("QID-2026-11-01-A", "OPP-A", "1"))
        result = compare(x, y)
        self.assertEqual(result["invalid_process_rows"], 1)
        self.assertEqual(result["ambiguous_or_missing_evidence"], 1)

    def test_misaligned_sheet_ranges_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "CROSSWALK_COLUMN_PARITY"):
            exact_qid_index([["QID-2026-11-01-A"], ["OPP-A"], []])

    def test_perfect_qid_parity_still_does_not_verify_quote_price(self):
        source = columns(("QID-2026-11-01-A", "OPP-A", "1"))
        result = compare(source, source)
        self.assertEqual(result["status"], "QID_PARITY_ONLY")
        self.assertFalse(result["source_process_report_certifies_quote_header"])
        self.assertFalse(result["quote_price_verified"])


if __name__ == "__main__":
    unittest.main()
