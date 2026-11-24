"""Invesco QQQ original 2018 distribution API forensic contracts."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
import unittest
import issuer_qqq2018_invesco_api as q

def raw_one():
    return json.dumps({"cusip":"46090E103","distributions":[{
        "exDate":"2018-06-18","recordDate":"2018-06-19",
        "payDate":"2018-07-31",
        "distributionAmountPerUnit":"0.37837",
        "ordinaryIncomeDistribution":"0.37837"
    },{
        "exDate":"2018-03-19","distributionAmountPerUnit":"0.0"
    }]}).encode()

class InvescoOriginalAPITests(unittest.TestCase):
    def test_direct_issuer_event_observed_but_no_cash_factor_certification(self):
        with TemporaryDirectory() as d:
            r=q.collect(getter=lambda url:raw_one(),out_dir=d)
            self.assertEqual(r["status"],"ISSUER_API_2018_EVENT_OBSERVED_CASH_FINALITY_HOLD")
            self.assertEqual(r["issuer_api_target_row"]["reported_distribution_amount_per_unit_usd"],
                             "0.37837")
            self.assertEqual(r["issuer_api_target_row"]["pay_date"],"2018-07-31")
            self.assertEqual(r["source_sha256"],sha256(raw_one()).hexdigest())
            self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),raw_one())
            self.assertFalse(r["issuer_2018_cash_finality_certified"])
            self.assertFalse(r["issuer_2018_payment_settlement_certified"])
            self.assertFalse(r["source_share_unit_basis_certified"])
            self.assertEqual(r["source_finality_verified_assets"],0)

    def test_api_empty_history_is_not_payment_denial(self):
        r=q.collect(getter=lambda url: b'{"distributions":[]}')
        self.assertEqual(r["status"],"ISSUER_API_2018_EVENT_NOT_IN_CURRENT_HISTORY_HOLD")
        self.assertIsNone(r["issuer_api_target_row"])
        self.assertFalse(r["historical_nonpayment_proven"])
        self.assertFalse(r["source_history_completeness_certified"])

    def test_api_malformed_or_wrong_cusip_preserves_raw_sha(self):
        for raw,err in (
            (b'<html>blocked</html>',"INVALID_JSON"),
            (b'{"distributions":{}}',"INVESCO_DISTRIBUTIONS_MISSING"),
            (b'{"cusip":"NOTQQQ","distributions":[]}',"INVESCO_PAYLOAD_CUSIP_MISMATCH"),
        ):
            with TemporaryDirectory() as d:
                r=q.collect(getter=lambda url,r=raw:r,out_dir=d)
                self.assertEqual(r["status"],"ISSUER_JSON_SCHEMA_REJECTED_RAW_ARCHIVED_HOLD")
                self.assertEqual(r["fetch_or_schema_failure_code"],err)
                self.assertEqual(r["source_sha256"],sha256(raw).hexdigest())
                self.assertEqual(gzip.decompress((Path(d)/r["source_archive"]).read_bytes()),raw)
                self.assertFalse(r["issuer_2018_cash_finality_certified"])

    def test_bad_duplicate_2018_events_are_rejected(self):
        doc=json.loads(raw_one())
        doc["distributions"].append(doc["distributions"][0])
        with TemporaryDirectory() as d:
            r=q.collect(getter=lambda url:json.dumps(doc).encode(),out_dir=d)
            self.assertEqual(r["status"],"ISSUER_JSON_SCHEMA_REJECTED_RAW_ARCHIVED_HOLD")
            self.assertEqual(r["fetch_or_schema_failure_code"],"INVESCO_DUPLICATE_2018_EVENT")

    def test_http_406_rotates_only_pinned_identical_request_parameters(self):
        seen=[]
        def fetch(url):
            seen.append(url)
            if len(seen)==1:
                raise HTTPError(url,406,"cached WAF refusal",None,None)
            return raw_one()
        r=q.collect(getter=fetch)
        self.assertEqual(seen,list(q.URLS))
        self.assertEqual(r["http_attempt_errors"],["HTTP_406"])
        self.assertEqual(r["used_source_url"],q.URLS[1])
        self.assertTrue(r["issuer_api_target_row"])
        self.assertFalse(r["issuer_2018_cash_finality_certified"])

    def test_http_status_failure_and_pr_offline(self):
        def unavailable(url):
            raise HTTPError(url,403,"blocked",None,None)
        r=q.collect(getter=unavailable)
        self.assertEqual(r["status"],"ISSUER_JSON_TRANSPORT_FAILED_HOLD")
        self.assertEqual(r["fetch_or_schema_failure_code"],"HTTP_403")
        self.assertIsNone(r["source_sha256"])
        offline=q.collect(offline=True,getter=lambda url: (_ for _ in ()).throw(
            AssertionError("PR source access forbidden")))
        self.assertEqual(offline["status"],"OFFLINE_ISSUER_JSON_UNFETCHED_HOLD")

    def test_url_and_date_identity_contracts(self):
        self.assertTrue(all(url.startswith("https://dng-api.invesco.com/")
                            and "46090E103" in url for url in q.URLS))
        self.assertEqual(q.iso_date("2018-06-18T00:00:00"),"2018-06-18")
        self.assertIsNone(q.iso_date("2018-13-18"))
        self.assertEqual(q.usd_as_published("0.37837"),"0.37837")
        self.assertIsNone(q.usd_as_published("-1"))

if __name__=="__main__":
    unittest.main()
