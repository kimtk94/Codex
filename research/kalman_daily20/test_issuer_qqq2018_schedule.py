"""Original QQQ trust rule: first-party date evidence cannot certify paid cash."""
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip
from hashlib import sha256
import unittest

import issuer_qqq2018_schedule as q

DOCUMENT = ("""
<html><body>
AMENDMENT NO. 6 TO THE STANDARD TERMS AND CONDITIONS OF TRUST
This Amendment No. 6 to the Standard Terms and Conditions of Trust,
dated as of January 26, 2018, by and between
Invesco PowerShares Capital Management LLC, as sponsor, and
The Bank of New York Mellon, as trustee.
The regular quarterly ex-dividend date for PowerShares QQQ Trust will
be the first Business Day subsequent to the third Friday in each of
March, June, September and December.
The dividend distribution, if any, is subject to accumulated income.
</body></html>""").encode()

class QQQIssuerScheduleTests(unittest.TestCase):
    def test_june_2018_calendar_exact(self):
        self.assertEqual(q.third_friday(2018, 6).isoformat(), "2018-06-15")
        self.assertEqual(q.expected_exdate(2018, 6), "2018-06-18")
        with self.assertRaisesRegex(ValueError,"QQQ_NON_QUARTERLY_MONTH"):
            q.expected_exdate(2018, 5)
        with self.assertRaisesRegex(ValueError,"QQQ_RULE_NOT_EXTENDED"):
            q.expected_exdate(2020, 6)

    def test_2018_issuer_original_archived_without_cash_promotion(self):
        with TemporaryDirectory() as d:
            r=q.build_report(getter=lambda url: DOCUMENT, outdir=d)
            self.assertEqual(r["status"], "FIRST_PARTY_2018_RULE_VERIFIED_CASH_HOLD")
            self.assertTrue(r["source_anchor_verified"])
            self.assertEqual(r["source_sha256"],sha256(DOCUMENT).hexdigest())
            body = gzip.decompress((Path(d)/r["source_archive"]).read_bytes())
            self.assertEqual(body,DOCUMENT)
            self.assertTrue(r["matched_qqq_exception_date"])
            self.assertIsNone(r["issuer_paid_cash_amount_usd"])
            self.assertFalse(r["issuer_cash_payment_certified"])
            self.assertFalse(r["issuer_distribution_declared_for_case"])
            self.assertEqual(r["source_finality_verified"],0)
            self.assertFalse(r["strategy_promoted"])

    def test_lookalike_unsigned_claim_is_not_first_party_attested(self):
        altered=DOCUMENT.replace(b"The Bank of New York Mellon", b"Imaginary Trustee")
        r=q.build_report(getter=lambda url:altered)
        self.assertEqual(r["status"],"FIRST_PARTY_RULE_SOURCE_ANCHORS_MISSING_HOLD")
        self.assertFalse(r["source_anchor_verified"])
        self.assertFalse(r["issuer_cash_payment_certified"])

    def test_failed_source_and_pr_offline_keep_hold(self):
        def unreachable(url):
            raise OSError("source unavailable")
        self.assertEqual(q.build_report(getter=unreachable)["status"],
                         "ISSUER_RULE_SOURCE_FETCH_OR_PARSE_FAILED_HOLD")
        r=q.build_report(offline=True,getter=lambda url: (_ for _ in ()).throw(
            AssertionError("offline fetched source")))
        self.assertEqual(r["status"],"OFFLINE_NO_DOCUMENT_HOLD")
        self.assertIsNone(r["source_sha256"])

if __name__=="__main__":
    unittest.main()
