"""Contracts for QQQ/QLD issuer-vendor conflict without payment promotion."""
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import issuer_ca_provider_reconciliation as v
import issuer_qqq2018_schedule as qqq

MANIFEST=json.loads((Path(__file__).parent/"issuer_ca_secondary_vendor_lineage.json").read_text())

class CrossVendorAuditTests(unittest.TestCase):
    def fixture(self, root, *, qld_exdate=None, with_sources=True):
        root=Path(root)
        qld=root/"issuer_qld2023_api"
        qqqroot=root/"issuer_qqq2018_rule"
        qld.mkdir()
        qqqroot.mkdir()
        rows=[{"Symbol":"QLD", "ExDate":"2023-12-20T00:00:00",
               "Dividend":"0.039111", "CashDividendPerShare":0.039111,
               "RecordDate":"2023-12-21T00:00:00", "PayableDate":"2023-12-28T00:00:00"}]
        if qld_exdate:
            rows.append({"Symbol":"QLD","ExDate":qld_exdate,
                         "Dividend":"0.176282","CashDividendPerShare":"0.176282"})
        body=json.dumps(rows).encode()
        rule_body=(
            "<html>Amendment No. 6 to the Trust agreement, dated as of "
            "January 26, 2018 between Invesco PowerShares Capital Management LLC "
            "and The Bank of New York Mellon. " + qqq.ANCHOR + "</html>"
        ).encode()
        qldreport={
            "issuer_payment_finality_certified":False,
            "historical_nonpayment_proven":False,
            "source_sha256":sha256(body).hexdigest() if with_sources else None,
            "source_archive":"qld_2023_proshares_api_raw_response.bin.gz" if with_sources else None,
            "status":("ISSUER_API_2023_TARGET_ROW_PRESENT_CASH_UNCERTIFIED"
                      if qld_exdate else "ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD")
                      if with_sources else "PR_OFFLINE_NO_SOURCE_HOLD",
            "api_2023_row_count":len(rows) if with_sources else None,
            "api_ex_dates":sorted([r["ExDate"][:10] for r in rows]) if with_sources else None,
            "issuer_api_target_row":{"ex_date":"2023-09-20"} if qld_exdate and with_sources else None,
        }
        qqqreport={
            "issuer_cash_payment_certified":False,
            "source_sha256":sha256(rule_body).hexdigest() if with_sources else None,
            "source_archive":"qqq_2018_amendment_6_original.html.gz" if with_sources else None,
            "source_anchor_verified":with_sources,
            "rule_derived_ex_date":"2018-06-18",
        }
        if with_sources:
            (qld/qldreport["source_archive"]).write_bytes(gzip.compress(body))
            (qqqroot/qqqreport["source_archive"]).write_bytes(gzip.compress(rule_body))
        (qld/"report.json").write_text(json.dumps(qldreport))
        (qqqroot/"report.json").write_text(json.dumps(qqqreport))
        gap={
            "research_only":True,"production_writes":False,
            "source_finality_verified":0,"issuer_payments_certified":0,
            "events":[
                {"symbol":"QLD","ex_date":"2023-09-20",
                 "actual_payment_certified":False,
                 "split_new_shares_per_old":"2"},
                {"symbol":"QQQ","ex_date":"2018-06-18",
                 "actual_payment_certified":False,
                 "sec_2020_third_party_2018_q3_quote_usd":"0.37837",
                 "alpaca_2018_event_candidate_usd":"0.37638",
                 "sec_quote_minus_alpaca_usd":"0.00199"},
            ],
        }
        return qld,qqqroot,gap

    def test_live_issuer_api_absent_vs_vendor_candidates_hold(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d)
            r=v.run(MANIFEST,gap,qld,qqqroot)
            self.assertEqual(r["status"],"TWO_CORPORATE_ACTION_SOURCE_DISAGREEMENTS_HOLD")
            self.assertEqual(r["issuer_distribution_payments_certified"],0)
            self.assertEqual(r["source_finality_verified_assets"],0)
            qqqcase,qldcase=r["cases"]
            self.assertEqual(qldcase["status"],"ISSUER_API_2023_MISSING_VS_SECONDARY_CANDIDATE_HOLD")
            self.assertEqual(qldcase["issuer_api_2023_ex_dates"],["2023-12-20"])
            self.assertTrue(qldcase["split_math_reconciles_to_publisher_precision"])
            self.assertEqual(qldcase["issuer_archive_grade"],"ARCHIVED_ORIGINAL_BYTES_HASH_VERIFIED")
            self.assertEqual(len(qldcase["third_party_claims"]),2)
            self.assertFalse(qldcase["historical_nonpayment_proven"])
            self.assertFalse(qldcase["upstream_feed_independence_certified"])
            self.assertEqual(qqqcase["issuer_2018_schedule_archive_grade"],"ARCHIVED_ORIGINAL_BYTES_HASH_VERIFIED")
            self.assertTrue(qqqcase["issuer_2018_schedule_rule_verified"])
            self.assertFalse(qqqcase["source_cash_amount_certified"])

    def test_fetched_official_september_does_not_promote_adjustment(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d,qld_exdate="2023-09-20T00:00:00")
            r=v.run(MANIFEST,gap,qld,qqqroot)
            qldcase=r["cases"][1]
            self.assertTrue(qldcase["issuer_api_has_target_row"])
            self.assertEqual(qldcase["status"],"ISSUER_API_2023_PRESENT_BUT_PAYMENT_UNCERTIFIED_HOLD")
            self.assertFalse(qldcase["issuer_cash_payment_certified"])
            self.assertFalse(qldcase["issuer_adjustment_factor_certified"])

    def test_pr_offline_does_not_create_payment_or_nonpayment_evidence(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d,with_sources=False)
            r=v.run(MANIFEST,gap,qld,qqqroot)
            qldcase=r["cases"][1]
            self.assertIsNone(qldcase["issuer_api_2023_rows_revalidated"])
            self.assertIsNone(qldcase["issuer_api_has_target_row"])
            self.assertFalse(qldcase["historical_nonpayment_proven"])
            self.assertFalse(r["cases"][0]["issuer_2018_schedule_rule_verified"])
            self.assertEqual(qldcase["status"],"ISSUER_API_NOT_CAPTURED_HOLD")

    def test_tampered_archive_rejected(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d)
            (qld/"qld_2023_proshares_api_raw_response.bin.gz").write_bytes(gzip.compress(b"altered"))
            with self.assertRaisesRegex(ValueError,"CA_LINEAGE_SOURCE_SHA256_MISMATCH"):
                v.run(MANIFEST,gap,qld,qqqroot)

    def test_curated_vendor_pretending_to_be_issuer_or_wrong_upstream_rejected(self):
        changed=deepcopy(MANIFEST)
        changed["cases"][0]["observations"][0]["source_class"]="ISSUER_ORIGINAL"
        with self.assertRaisesRegex(ValueError,"UNCERTIFIED_VENDOR_OBSERVATION_INVALID"):
            v.validate_claims(changed)
        changed=deepcopy(MANIFEST)
        changed["cases"][0]["observations"][0]["attributed_upstream"]="ProShares"
        with self.assertRaisesRegex(ValueError,"UPSTREAM_MISATTRIBUTED"):
            v.validate_claims(changed)

    def test_unverified_payment_promoted_fails_closed(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d)
            gap["events"][0]["actual_payment_certified"]=True
            with self.assertRaisesRegex(ValueError,"CA_LINEAGE_PAYMENT_PROMOTED"):
                v.run(MANIFEST,gap,qld,qqqroot)

    def test_issuer_report_must_match_original_bytes(self):
        with TemporaryDirectory() as d:
            qld,qqqroot,gap=self.fixture(d)
            p=qld/"report.json"
            x=json.loads(p.read_text())
            x["api_ex_dates"]=["2023-09-20","2023-12-20"]
            p.write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,"CA_LINEAGE_QLD_API_REPORT_DISAGREES_WITH_BYTES"):
                v.run(MANIFEST,gap,qld,qqqroot)

if __name__=="__main__":
    unittest.main()
