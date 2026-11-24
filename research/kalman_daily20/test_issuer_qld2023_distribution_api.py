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
            self.assertEqual(r["issuer_api_target_row"]["cash_dividend_as_published_usd"],"0.176282")
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


    def test_invalid_html_is_archived_and_classified_as_schema_failure(self):
        original=b"<!DOCTYPE html><html><body>upstream unavailable</body></html>"
        with TemporaryDirectory() as d:
            r=q.run(getter=lambda url: original,out_dir=d)
            self.assertEqual(r["version"],"daily20-qld2023-issuer-distribution-api-v3")
            self.assertEqual(r["status"],"ISSUER_API_FETCH_OR_SCHEMA_FAILED_HOLD")
            self.assertEqual(r["fetch_error_code"],"QLD_API_INVALID_JSON")
            self.assertEqual(r["failure_stage"],"API_SCHEMA_VALIDATE")
            self.assertTrue(r["source_fetched_but_schema_rejected"])
            self.assertEqual(r["source_response_kind"],"HTML_OR_XML")
            self.assertEqual(r["source_sha256"],sha256(original).hexdigest())
            self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),original)
            self.assertIsNone(r["api_2023_row_count"])
            self.assertFalse(r["issuer_payment_finality_certified"])

    def test_bad_fund_schema_preserves_raw_bytes_with_explicit_reason(self):
        raw=b'[{"Symbol":"TQQQ","ExDate":"09/20/2023","Dividend":"0.176282"}]'
        with TemporaryDirectory() as d:
            r=q.run(getter=lambda url:raw,out_dir=d)
            self.assertEqual(r["fetch_error_code"],"QLD_API_SECURITY_ID_MISMATCH")
            self.assertEqual(r["failure_stage"],"API_SCHEMA_VALIDATE")
            self.assertEqual(r["source_response_kind"],"JSON_ARRAY_CANDIDATE")
            self.assertEqual(r["source_sha256"],sha256(raw).hexdigest())
            self.assertFalse(r["historical_nonpayment_proven"])

    def test_http_status_and_transport_do_not_fake_response_bytes(self):
        from urllib.error import HTTPError, URLError
        for exc,code in (
            (HTTPError(q.URL,403,"Forbidden",None,None),"HTTP_STATUS_403"),
            (URLError("network unavailable"),"URL_TRANSPORT_ERROR"),
            (ValueError("QLD_UNTRUSTED_SOURCE_REDIRECT"),"QLD_UNTRUSTED_SOURCE_REDIRECT")
        ):
            def fail(url,exc=exc):
                raise exc
            with TemporaryDirectory() as d:
                r=q.run(getter=fail,out_dir=d)
                self.assertEqual(r["fetch_error_code"],code)
                self.assertEqual(r["failure_stage"],"SOURCE_FETCH")
                self.assertIsNone(r["source_sha256"])
                self.assertIsNone(r["source_archive"])
                self.assertFalse(r["source_fetched_but_schema_rejected"])

    def test_cash_fields_disagree_remains_raw_hashed_and_hold(self):
        raw=b'[{"Symbol":"QLD","ExDate":"09/20/2023","Dividend":"0.1","CashDividendPerShare":"0.2"}]'
        with TemporaryDirectory() as d:
            r=q.run(getter=lambda url:raw,out_dir=d)
            self.assertEqual(r["fetch_error_code"],"QLD_API_CASH_FIELDS_DISAGREE")
            self.assertTrue(r["source_fetched_but_schema_rejected"])
            self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),raw)
            self.assertIsNone(r["issuer_api_target_row"])
            self.assertFalse(r["independent_adjustment_factor_certified"])


    def test_original_issuer_iso_datetime_example_absence_not_nonpayment(self):
        # Shape and decimal representations captured from ProShares' live
        # 2023 year-scoped API on 2026-11-22, not a user-provided cash guess.
        original=json.dumps([{
            "CashDividendPerShare":0.039111,
            "Dividend":".039111",
            "EffectiveDate":"2023-12-19T00:00:00",
            "ExDate":"2023-12-20T00:00:00",
            "PayableDate":"2023-12-28T00:00:00",
            "RecordDate":"2023-12-21T00:00:00",
            "Symbol":"QLD"
        }]).encode()
        with TemporaryDirectory() as d:
            r=q.run(getter=lambda url:original,out_dir=d)
            self.assertEqual(r["status"],"ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD")
            self.assertEqual(r["api_2023_row_count"],1)
            self.assertEqual(r["api_ex_dates"],["2023-12-20"])
            self.assertIsNone(r["issuer_api_target_row"])
            self.assertEqual(r["source_sha256"],sha256(original).hexdigest())
            self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),original)
            self.assertFalse(r["historical_nonpayment_proven"])
            self.assertFalse(r["historical_api_completeness_certified"])
            self.assertEqual(r["published_dividend_share_unit_basis"],
                             "UNDETERMINED_POSSIBLY_SPLIT_ADJUSTED")
            self.assertEqual(r["source_finality_verified"],0)

    def test_iso_datetime_date_not_rebased_to_utc_and_invalid_calendar_rejected(self):
        self.assertEqual(q.parse_day("2023-12-20T00:00:00"),"2023-12-20")
        self.assertEqual(q.parse_day("2023-09-20T00:00:00"),"2023-09-20")
        self.assertIsNone(q.parse_day("2023-13-20T00:00:00"))
        self.assertIsNone(q.parse_day("not a date"))
        rows,hit=q.inspect(json.dumps([{
            "Symbol":"QLD", "ExDate":"2023-09-20T00:00:00",
            "Dividend":".176282", "CashDividendPerShare":0.176282
        }]).encode())
        self.assertEqual(len(rows),1)
        self.assertEqual(hit["cash_dividend_as_published_usd"],"0.176282")
        self.assertFalse(hit["cash_share_unit_basis_certified"])

if __name__ == "__main__":
    unittest.main()
