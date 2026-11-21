"""ProShares QLD 2023 official API contract tests; never promote to LIVE."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import issuer_qld2023_distribution_api as q


class ProSharesDistributionAPITests(unittest.TestCase):
    def test_2023_issuer_event_present_is_only_source_observation(self):
        original=json.dumps([
          {"Symbol":"QLD","ExDate":"09/20/2023","RecordDate":"09/21/2023",
           "PayableDate":"09/27/2023","Dividend":"0.176282"},
          {"Symbol":"QLD","ExDate":"12/20/2023","Dividend":"0.078222"}
        ]).encode()
        with TemporaryDirectory() as d:
            r=q.run(getter=lambda url: original,out_dir=d)
            self.assertEqual(r["status"],"ISSUER_API_2023_TARGET_ROW_PRESENT_CASH_UNCERTIFIED")
            self.assertEqual(r["issuer_api_target_row"]["ex_date"],"2023-09-20")
            self.assertEqual(r["issuer_api_target_row"]["cash_dividend_per_2023_share_usd"],"0.176282")
            self.assertEqual(r["issuer_api_target_row"]["payable_date"],"2023-09-27")
            self.assertEqual(r["source_sha256"],sha256(original).hexdigest())
            self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),original)
            self.assertFalse(r["issuer_payment_finality_certified"])
            self.assertFalse(r["independent_adjustment_factor_certified"])
            self.assertFalse(r["historical_nonpayment_proven"])
            self.assertEqual(r["source_finality_verified"],0)

    def test_missing_2023_september_row_is_not_nonpayment_proof(self):
        r=q.run(getter=lambda url: json.dumps([
          {"Symbol":"QLD","ExDate":"12/20/2023","Dividend":"0.078222"}
        ]).encode())
        self.assertEqual(r["status"],"ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD")
        self.assertEqual(r["api_ex_dates"],["2023-12-20"])
        self.assertFalse(r["historical_nonpayment_proven"])
        self.assertIsNone(r["issuer_api_target_row"])

    def test_wrong_fund_year_or_schema_cannot_be_accepted(self):
        for payload in (
            b"<html>upstream blocked</html>",
            b'{"rows":[]}',
            b'[{"Symbol":"TQQQ","ExDate":"09/20/2023","Dividend":"0.176282"}]',
            b'[{"Symbol":"QLD","ExDate":"09/20/2024","Dividend":"0.176282"}]',
            b'[{"Symbol":"QLD","ExDate":"09/20/2023","Dividend":"-0.1"}]',
            b'[{"Symbol":"QLD","ExDate":"09/20/2023","Dividend":"0.1","CashDividendPerShare":"0.2"}]'
        ):
            result=q.run(getter=lambda url,p=payload:p)
            self.assertEqual(result["status"],"ISSUER_API_FETCH_OR_SCHEMA_FAILED_HOLD")
            self.assertFalse(result["issuer_payment_finality_certified"])

    def test_offline_no_network(self):
        r=q.run(offline=True, getter=lambda url: (_ for _ in ()).throw(
            AssertionError("offline network call")))
        self.assertEqual(r["status"],"PR_OFFLINE_NO_SOURCE_HOLD")
        self.assertIsNone(r["source_sha256"])


if __name__ == "__main__":
    unittest.main()
