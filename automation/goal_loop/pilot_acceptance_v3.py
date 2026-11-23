"""Independent V3 acceptance; execute model-authored target only in GitHub CI.

ALL inputs are synthetic. No SFDC, CRM, mail, user data, or production writes.
"""
import copy
import unittest

from automation.goal_loop.pilot_quote_summary_v3 import summarize_quotes


def row(quote_id, product_line, sample_count, unit_price_krw):
    return {
        "quote_id": quote_id,
        "product_line": product_line,
        "sample_count": sample_count,
        "unit_price_krw": unit_price_krw,
    }


class QuoteSummaryV3Acceptance(unittest.TestCase):
    def test_multi_product_totals_are_vat_exclusive_krw(self):
        rows = [
            row("Q-001", "mRNA", 2, 100000),
            row("Q-002", "WGS", 1, 800000),
            row("Q-003", "MRNA", 3, 100000),
        ]
        self.assertEqual(summarize_quotes(rows), {
            "totals_krw": {"MRNA": 500000, "WGS": 800000},
            "accepted": 3, "rejected": 0,
        })

    def test_duplicates_and_invalid_rows_are_rejected(self):
        rows = [
            row(" Q-010 ", "mRNA ", 2, 150000),
            row("Q-010", "WGS", 9, 999999),
            row("Q-011", "wgs", 1, 500000),
            row("", "WGS", 1, 500000),
            {"quote_id": "Q-012", "product_line": "WGS",
             "sample_count": True, "unit_price_krw": 500000},
            row("Q-013", "WGS", 1, -10),
            row("Q-014", "  ", 2, 100000),
            row("Q-015", "WGS", 0, 100000),
            "not-a-dictionary",
            {},
        ]
        self.assertEqual(summarize_quotes(rows), {
            "totals_krw": {"MRNA": 300000, "WGS": 500000},
            "accepted": 2, "rejected": 8,
        })

    def test_case_insensitive_product_grouping_and_stable_key_order(self):
        rows = [
            row("Q-101", " WGS ", 1, 150),
            row("Q-102", "mrna", 1, 200),
            row("Q-103", "MrNa", 1, 300),
            row("Q-104", "wgs", 1, 50),
        ]
        result = summarize_quotes(rows)
        self.assertEqual(result["totals_krw"], {"MRNA": 500, "WGS": 200})
        self.assertEqual(list(result["totals_krw"]), ["MRNA", "WGS"])
        self.assertEqual((result["accepted"], result["rejected"]), (4, 0))

    def test_zero_price_is_valid_and_boolean_price_is_invalid(self):
        rows = [
            row("Q-201", "Olink", 5, 0),
            row("Q-202", "Olink", 1, False),
            row("Q-203", "Olink", False, 20000),
            row("Q-204", "Olink", -1, 20000),
            row("Q-205", "Olink", 1, 20000),
        ]
        self.assertEqual(summarize_quotes(rows), {
            "totals_krw": {"OLINK": 20000}, "accepted": 2, "rejected": 3,
        })

    def test_no_mutation_and_duplicate_only_after_valid_record(self):
        rows = [
            row("Q-301", "mRNA", 0, 100),
            row("Q-301", "mRNA", 2, 100),
            row(" Q-301 ", "mRNA", 1, 50000),
            row("q-301", "mRNA", 1, 300),
        ]
        frozen = copy.deepcopy(rows)
        self.assertEqual(summarize_quotes(rows), {
            "totals_krw": {"MRNA": 500}, "accepted": 2, "rejected": 2,
        })
        self.assertEqual(rows, frozen)

    def test_nonlist_input_is_rejected_explicitly(self):
        for invalid in (None, "Q-001", {}, (), 10):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                summarize_quotes(invalid)

    def test_empty_list(self):
        self.assertEqual(summarize_quotes([]), {
            "totals_krw": {}, "accepted": 0, "rejected": 0,
        })

    def test_large_krw_exact_arithmetic(self):
        self.assertEqual(summarize_quotes([
            row("Q-888", "WGS", 1000, 123456789),
        ]), {"totals_krw": {"WGS": 123456789000},
              "accepted": 1, "rejected": 0})


if __name__ == "__main__":
    unittest.main()
