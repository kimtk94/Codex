"""First-party fiscal-year evidence cannot certify a single QQQ cash event."""
import gzip
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import issuer_qqq2018_fiscal as q

DOC = b"""<html><body>
Invesco QQQ Trust, Series 1
Financial Highlights
Invesco QQQ Trust, Series 1 (QQQ)
Year Ended September 30,
2018 2017 2016 2015 2014
Per Share Operating Performance:
Net investment income 1.42 1.33
Distributions to Shareholders from:
Net investment income (1.31) (1.33) (1.24) (1.15)
Net asset value at end of year $185.73
Notes to Financial Statements
</body></html>"""


class QQQFiscalTests(unittest.TestCase):
    def test_exact_fiscal_row_is_issuer_context_not_single_date(self):
        with TemporaryDirectory() as temp:
            r = q.audit(getter=lambda url: DOC, out_dir=temp)
            self.assertEqual(r["status"], "ISSUER_FY2018_AGGREGATE_VERIFIED_20180618_CASH_HOLD")
            self.assertEqual(r["fy2018_distributions_per_share_usd"], "1.31")
            self.assertEqual(r["report_fiscal_year_end"], "2018-09-30")
            self.assertEqual(r["case_ex_date"], "2018-06-18")
            self.assertTrue(r["fy2018_financial_highlights_row_verified"])
            self.assertIsNone(r["qqq_2018_06_18_specific_cash_usd_certified"])
            self.assertFalse(r["issuer_single_event_amount_certified"])
            self.assertFalse(r["fiscal_total_is_event_payment_amount"])
            self.assertFalse(r["independent_adjustment_factor_certified"])
            self.assertFalse(r["strategy_promoted"])
            self.assertEqual(r["source_sha256"], sha256(DOC).hexdigest())
            saved = Path(temp) / r["original_html_gzip"]
            self.assertEqual(gzip.decompress(saved.read_bytes()), DOC)

    def test_wrong_fiscal_year_is_not_promoted(self):
        bad = DOC.replace(b"2018 2017 2016", b"2017 2016 2015")
        r = q.audit(getter=lambda url: bad)
        self.assertEqual(r["status"], "ISSUER_FY2018_ROW_NOT_VERIFIED_HOLD")
        self.assertIsNone(r["fy2018_distributions_per_share_usd"])

    def test_wrong_year_amount_is_not_promoted(self):
        bad = DOC.replace(b"Net investment income (1.31)", b"Net investment income (1.30)")
        r = q.audit(getter=lambda url: bad)
        self.assertEqual(r["status"], "ISSUER_FY2018_ROW_NOT_VERIFIED_HOLD")
        self.assertFalse(r["issuer_single_event_amount_certified"])

    def test_missing_issuer_identity_is_not_promoted(self):
        bad = DOC.replace(b"Invesco QQQ Trust", b"unrelated issuer")
        r = q.audit(getter=lambda url: bad)
        self.assertFalse(r["fy2018_financial_highlights_row_verified"])
        self.assertEqual(r["status"], "ISSUER_FY2018_ROW_NOT_VERIFIED_HOLD")

    def test_irrelevant_one_point_three_one_elsewhere_not_counted(self):
        bad = DOC.replace(b"Net investment income (1.31)", b"Net investment income (1.32)")
        bad += b"<p>1.31 was observed in another unrelated context</p>"
        r = q.audit(getter=lambda url: bad)
        self.assertIsNone(r["fy2018_distributions_per_share_usd"])

    def test_offline_and_network_failure_remain_hold(self):
        r = q.audit(offline=True, getter=lambda url: (_ for _ in ()).throw(
            AssertionError("Unexpected network access")))
        self.assertEqual(r["status"], "PR_OFFLINE_NO_FIRST_PARTY_REPORT_HOLD")
        self.assertIsNone(r["source_sha256"])
        def fail(url):
            raise OSError("sensitive irrelevant remote response")
        r2 = q.audit(getter=fail)
        self.assertEqual(r2["status"], "ISSUER_FY2018_SOURCE_OR_ARCHIVE_ERROR_HOLD")
        self.assertEqual(r2["error_code"], "OSError")
        self.assertNotIn("sensitive", str(r2))
        self.assertFalse(r2["issuer_single_event_amount_certified"])


if __name__ == "__main__":
    unittest.main()
