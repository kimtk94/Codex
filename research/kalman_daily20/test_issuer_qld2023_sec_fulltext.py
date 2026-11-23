"""Contracts for pinned 71MB QLD 2023 SEC N-CSRS full-text inspection."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import issuer_qld2023_sec_fulltext as q


def issuer_index():
    return {"cases":[{
        "source_id":"QLD_2023_09",
        "source_status":"SEC_FIXED_HISTORICAL_FILING_METADATA_VERIFIED_CASH_HOLD",
        "metadata_identity_verified":True,
        "underlying_report_url":q.SEC_URL,
        "underlying_report_cash_ledger_examined":False,
        "historical_issuer_event_paid_cash_certified":False,
    }]}


def original_document():
    # Simulated 2023 trust-wide SEC HTML, not actual financial evidence.
    return (b"<!DOCTYPE html><html><body>" +
            b"<h1>ProShares Ultra QQQ</h1><p>November 30, 2023</p>" +
            b"<p>Financial Highlights</p><p>Distributions to shareholders</p>" +
            b"<p>September 20, 2023 0.176282</p>" +
            b"<p>Another ETF, September 20, 2023, 0.088141</p>" +
            b"<p>QID and other funds</p>" + b"x"*16_000 +
            b"</body></html>")


def fake_source(body):
    def fetch(path):
        path=Path(path)
        path.write_bytes(gzip.compress(body,mtime=0))
        return {"source_sha256":sha256(body).hexdigest(),
                "source_bytes":len(body),
                "archive_bytes":path.stat().st_size,
                "source_acquisition":"LIVE_SEC_FIXED_ORIGINAL"}
    return fetch


class SECFullTextTests(unittest.TestCase):
    def test_scanned_filing_still_never_certifies_specific_payout(self):
        with TemporaryDirectory() as d:
            x=q.collect(index_report=issuer_index(),out_dir=d,
                        fetcher=fake_source(original_document()))
            self.assertEqual(x["status"],"SEC_FULLTEXT_SCANNED_UNSCOPED_PAYMENT_HOLD")
            self.assertTrue(x["document_anchors_present"])
            self.assertEqual(x["source_sha256"],sha256(original_document()).hexdigest())
            self.assertEqual(x["source_bytes"],len(original_document()))
            self.assertTrue(x["unscoped_full_filing_text_term_counts"]
                            ["sept_exdate_words"]["total_unscoped_hits"]>=1)
            self.assertTrue(x["unscoped_full_filing_text_term_counts"]
                            ["candidate_original_dividend"]["total_unscoped_hits"]>=1)
            self.assertFalse(x["issuer_event_cash_certified"])
            self.assertFalse(x["historical_nonpayment_proven"])
            self.assertEqual(x["source_finality_verified_assets"],0)

    def test_no_payout_text_does_not_prove_nonpayment(self):
        body=original_document().replace(b"0.176282",b"0.000000")
        with TemporaryDirectory() as d:
            x=q.collect(index_report=issuer_index(),out_dir=d,fetcher=fake_source(body))
            self.assertEqual(x["status"],"SEC_FULLTEXT_SCANNED_UNSCOPED_PAYMENT_HOLD")
            self.assertEqual(x["unscoped_full_filing_text_term_counts"]
                             ["candidate_original_dividend"]["total_unscoped_hits"],0)
            self.assertFalse(x["historical_nonpayment_proven"])

    def test_bad_or_missing_sec_index_never_fetches_71mb(self):
        with TemporaryDirectory() as d:
            x=q.collect(index_report={},out_dir=d,
                        fetcher=lambda path: (_ for _ in ()).throw(
                            AssertionError("index must gate network")))
            self.assertEqual(x["status"],"SEC_INDEX_UNVERIFIED_FULLTEXT_HOLD")
            self.assertIsNone(x["source_sha256"])
            y=q.collect(offline=True,index_report=issuer_index(),out_dir=d,
                        fetcher=lambda path: (_ for _ in ()).throw(
                            AssertionError("PR offline must not fetch")))
            self.assertEqual(y["status"],"OFFLINE_NO_SEC_FULLTEXT_HOLD")

    def test_compressed_original_hash_tampering_rejected(self):
        with TemporaryDirectory() as d:
            path=Path(d)/q.ARCHIVE_NAME
            path.write_bytes(gzip.compress(original_document(),mtime=0))
            with self.assertRaisesRegex(ValueError,"QLD_SEC_SOURCE_DIGEST_MISMATCH"):
                q.unpack_verified(path,"0"*64)

    def test_immutable_previous_zip_cache_verified_and_reused(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            fresh=root/"fresh"
            x=q.collect(index_report=issuer_index(),out_dir=fresh,
                        fetcher=fake_source(original_document()))
            prior=root/"prior.zip"
            with ZipFile(prior,"w") as z:
                z.writestr(q.RESULT_FOLDER+"/report.json",json.dumps(x))
                z.write(fresh/q.ARCHIVE_NAME,q.RESULT_FOLDER+"/"+q.ARCHIVE_NAME)
            restored=q.collect(index_report=issuer_index(),out_dir=root/"restored",
                               previous_zip=prior,
                               fetcher=lambda path: (_ for _ in ()).throw(
                                   AssertionError("immutable cache must avoid HTTP")))
            self.assertEqual(restored["source_acquisition"],
                             "VERIFIED_IMMUTABLE_PRIOR_ARCHIVE")
            self.assertEqual(restored["source_sha256"],x["source_sha256"])
            self.assertFalse(restored["issuer_event_cash_certified"])

    def test_not_html_and_bounded_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"QLD_SEC_NOT_HTML"):
            q.scan(b"not valid html")
        with TemporaryDirectory() as d:
            path=Path(d)/q.ARCHIVE_NAME
            path.write_bytes(gzip.compress(b"<!DOCTYPE html><p>short</p>",mtime=0))
            with self.assertRaisesRegex(ValueError,"QLD_SEC_RAW_SIZE_INVALID"):
                q.unpack_verified(path)


    def test_original_edgar_sgml_financial_statements_show_zero_qlD_distributions(self):
        trust_six_month=(
            "ULTRA QQQ Ultra Real Estate Ultra Russell2000 "
            "Six Months Ended November 30, 2023 (Unaudited) "
            "Year Ended May 31, 2023 "
            "FROM INVESTMENT ACTIVITIES: OPERATIONS: "
            "Net investment income (loss) $ 2,256,829 $ 32,731,163 "
            "DISTRIBUTIONS TO SHAREHOLDERS FROM: Distributable earnings "
            "— (7,280,372) (419,095) (850,792) "
            "Total distributions — (7,280,372) (419,095) (850,792) "
        )
        highlights=(
            "Financial Highlights Ultra QQQ Six Months ended November 30, 2023 "
            "(Unaudited) $ 57.26 $ 0.03 $ 11.43 $ — $ 11.46 "
            "$ — $ — $ — $ — $ 68.72 20.00 % "
            "Year ended May 31, 2023 50.68 0.45 6.24 "
            "(0.11) (0.11) 57.26 "
            "Year ended May 31, 2022 63.62"
        )
        raw=(
            "<DOCUMENT>\n<TYPE>N-CSRS\n<SEQUENCE>1\n"
            "<FILENAME>primary-document.htm\n<TEXT>\n"
            "<html><body><p>ProShares Ultra QQQ November 30, 2023</p>"
            "<p>"+trust_six_month+"</p><p>"+highlights+"</p>"
            +"<p>"+"Y"*12000+"</p></body></html>\n</TEXT>\n</DOCUMENT>"
        ).encode("utf-8")
        with TemporaryDirectory() as d:
            x=q.collect(index_report=issuer_index(),out_dir=d,
                        fetcher=fake_source(raw))
            self.assertEqual(x["status"],
                             "SEC_QLD_2023_PERIOD_ZERO_DISTRIBUTIONS_ACCOUNTING_HOLD")
            self.assertEqual(x["sec_document_envelope_format"],"EDGAR_SGML_N_CSRS_TEXT_HTML")
            self.assertTrue(x["qld_statement_changes_fund_column_pinned"])
            self.assertEqual(x["qld_statement_prior_fy_distributions_usd"],"7,280,372")
            self.assertTrue(x["qld_statement_2023_period_total_distributions_reported_zero"])
            self.assertTrue(x["qld_financial_highlights_fund_row_pinned"])
            self.assertTrue(
                x["qld_financial_highlights_2023_period_per_share_distributions_reported_zero"])
            self.assertTrue(x["qld_issuer_period_zero_distributions_two_statement_agreement"])
            self.assertFalse(x["issuer_event_cash_certified"])
            self.assertFalse(x["historical_nonpayment_proven"])
            self.assertEqual(x["source_sha256"],sha256(raw).hexdigest())

    def test_mismatched_financial_statement_columns_downgrade_to_unscoped_hold(self):
        body=(
            "<html><body><p>Ultra QQQ November 30, 2023 Financial Highlights</p>"
            "<p>Ultra QQQ Ultra Real Estate Ultra Russell2000 "
            "Six Months Ended November 30, 2023 "
            "DISTRIBUTIONS TO SHAREHOLDERS FROM: "
            "Distributable earnings 0.176282 (7,280,372) "
            "Total distributions 0.176282 (7,280,372)</p>"
            "<p>Ultra QQQ Six Months ended November 30, 2023 (Unaudited) "
            "$ 57.26 $ 0.03 $ 11.43 $ — $ 11.46 "
            "$ — $ — $ — $ — $ 68.72 "
            "Year ended May 31, 2023 50.68 "
            "Year ended May 31, 2022 63.62</p>"
            +"x"*12000+"</body></html>"
        ).encode()
        with TemporaryDirectory() as d:
            r=q.collect(index_report=issuer_index(),out_dir=d,fetcher=fake_source(body))
            self.assertEqual(r["status"],"SEC_FULLTEXT_SCANNED_UNSCOPED_PAYMENT_HOLD")
            self.assertFalse(r["qld_issuer_period_zero_distributions_two_statement_agreement"])
            self.assertFalse(r["issuer_event_cash_certified"])

    def test_bad_sgml_parser_still_preserves_full_original_digest(self):
        bad=(
            b"<DOCUMENT>\n<TYPE>N-CSRS\n<FILENAME>primary-document.htm\n"
            b"<TEXT><html>Ultra QQQ</html></TEXT></WRONG>"
            +b"x"*12000
        )
        with TemporaryDirectory() as d:
            x=q.collect(index_report=issuer_index(),out_dir=d,fetcher=fake_source(bad))
            self.assertEqual(x["status"],"SEC_FULLTEXT_FETCH_OR_VALIDATE_FAILED_HOLD")
            self.assertEqual(x["source_failure_code"],
                             "QLD_SEC_NOT_HTML_OR_PINNED_EDGAR_SGML")
            self.assertEqual(x["source_sha256"],sha256(bad).hexdigest())
            self.assertEqual(x["source_archive"],q.ARCHIVE_NAME)
            self.assertEqual(gzip.decompress((Path(d)/q.ARCHIVE_NAME).read_bytes()),bad)
            self.assertFalse(x["issuer_event_cash_certified"])

if __name__=="__main__":
    unittest.main()
