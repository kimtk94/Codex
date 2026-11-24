"""SEC filing index provenance: fixed accession dates, never event cash."""
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip
import json
from hashlib import sha256
import unittest

import issuer_historical_edgar as e


def html_for(source_id):
    case=e.CASES[source_id]
    return ("<html><body><h1>SEC filing detail</h1>" +
            " | ".join(case["required"]) + "</body></html>").encode()

class HistoricalEdgarTests(unittest.TestCase):
    def test_both_issuer_filing_anchors_hash_and_archive(self):
        raw={case["url"]:html_for(i) for i,case in e.CASES.items()}
        with TemporaryDirectory() as d:
            x=e.collect(getter=lambda url:raw[url],out_dir=d)
            self.assertEqual(len(x["cases"]),2)
            self.assertFalse(x["issuer_cash_payment_certified"])
            self.assertEqual(x["source_finality_verified_assets"],0)
            self.assertFalse(x["mutable_pdf_historical_certification"])
            for item in x["cases"]:
                self.assertEqual(item["source_status"],
                                 "SEC_FIXED_HISTORICAL_FILING_METADATA_VERIFIED_CASH_HOLD")
                self.assertTrue(item["metadata_identity_verified"])
                self.assertFalse(item["historical_issuer_event_paid_cash_certified"])
                self.assertFalse(item["underlying_report_cash_ledger_examined"])
                self.assertEqual(item["source_sha256"],sha256(raw[item["url"]]).hexdigest())
                self.assertEqual(gzip.decompress((Path(d)/item["source_archive"]).read_bytes()),
                                 raw[item["url"]])

    def test_missing_2023_period_or_fund_identity_fails_closed(self):
        src=html_for("QLD_2023_09")
        for wrong in (b"2024-11-30",b"C000018466"):
            raw=src.replace(b"2023-11-30" if wrong.startswith(b"2024") else b"C000018465",wrong)
            facts=e.verify("QLD_2023_09",raw)
            self.assertFalse(facts["metadata_identity_verified"])

    def test_qld_filing_index_not_misrepresented_as_payment_ledger(self):
        case=e.CASES["QLD_2023_09"]
        self.assertEqual(case["underlying_report_bytes_claimed_by_index"],71373267)
        self.assertFalse(case["underlying_report_cash_ledger_examined"])
        self.assertEqual(case["event_ex_date"],"2023-09-20")
        self.assertIn("2023_11_30_NCSRS",case["evidence_scope"])
        self.assertNotEqual(e.DYNAMIC_ALIAS,case["url"])

    def test_network_failure_and_pr_offline_do_not_generate_raw(self):
        with TemporaryDirectory() as d:
            x=e.collect(offline=True,getter=lambda url: (_ for _ in ()).throw(
                AssertionError("PR must be offline")),out_dir=d)
            self.assertTrue(all(c["source_archive"] is None for c in x["cases"]))
            self.assertTrue(all(c["metadata_identity_verified"] is False for c in x["cases"]))
        with TemporaryDirectory() as d:
            x=e.collect(getter=lambda url: (_ for _ in ()).throw(
                OSError("unavailable")),out_dir=d)
            self.assertTrue(all(c["source_status"] ==
                                "SEC_FIXED_FILING_FETCH_OR_PARSE_FAILED_HOLD"
                                for c in x["cases"]))
            self.assertTrue(all(c["source_sha256"] is None for c in x["cases"]))

    def test_event_amount_never_auto_certified_even_if_page_mentions_number(self):
        raw={case["url"]:html_for(i)+b"<p>0.37837 0.176282</p>"
             for i,case in e.CASES.items()}
        result=e.collect(getter=lambda url:raw[url])
        self.assertTrue(all(c["metadata_identity_verified"] for c in result["cases"]))
        self.assertFalse(result["issuer_cash_payment_certified"])
        self.assertFalse(result["independent_adjustment_factor_certified"])
        self.assertFalse(result["historical_nonpayment_proven"])

if __name__=="__main__":
    unittest.main()
