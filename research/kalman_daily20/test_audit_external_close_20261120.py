"""No after-hours quote can substitute for a regular market close."""
from __future__ import annotations
import unittest
from audit_external_close_20261120 import (
    AFTER_HOURS, REGULAR, CONTRADICTORY_REGULAR,
    CLOSE_TOL_USD, compare_frozen_quote, validate_quote_type
)

class PublicCloseContracts(unittest.TestCase):
    def test_two_distinct_published_source_urls_each(self):
        self.assertEqual(len(REGULAR),7)
        self.assertTrue(all(len(urls)>=2 and len(set(urls))>=2
                            for _,urls in REGULAR.values()))

    def test_late_archive_regular_and_early_archive_afterhours_are_distinct(self):
        for name,(price,url) in AFTER_HOURS.items():
            self.assertFalse(compare_frozen_quote(
                price,REGULAR[name][0],label="REGULAR_CLOSE"))
            self.assertTrue(compare_frozen_quote(
                price,price,label="AFTER_HOURS"))
        self.assertEqual(len(AFTER_HOURS),5)

    def test_half_cent_precision(self):
        self.assertTrue(compare_frozen_quote(
            689.809998,689.81,label="REGULAR_CLOSE"))
        self.assertFalse(compare_frozen_quote(
            63.53,63.52,label="REGULAR_CLOSE"))
        self.assertEqual(CLOSE_TOL_USD,.005)

    def test_quote_type_has_no_default(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_QUOTE_TYPE_UNDEFINED"):
            validate_quote_type("LATEST_PRICE")
        with self.assertRaisesRegex(ValueError,"SOURCE_QUOTE_TYPE_UNDEFINED"):
            compare_frozen_quote(697.49,697.49,label="CLOSE")

    def test_disagreement_sources_preserved(self):
        self.assertEqual(CONTRADICTORY_REGULAR["SPY"][0],690.87)
        self.assertEqual(CONTRADICTORY_REGULAR["QLD"][0],63.53)
        for symbol,(price,url) in CONTRADICTORY_REGULAR.items():
            self.assertNotAlmostEqual(price,REGULAR[symbol][0],places=2)
            self.assertIn("https://",url)

if __name__=="__main__":
    unittest.main()
