"""Contracts: historical issuer context cannot auto-promote CA payment events."""
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from issuer_ca_gap_audit import audit


class IssuerGapAuditTests(unittest.TestCase):
    def fixture(self, directory):
        base = Path(directory) / "issuer_ca_primary"
        (base / "raw").mkdir(parents=True)
        sources = {}
        for sid, symbol, day in (
            ("QQQ_2018_SEC_2020_Q3_TABLE", "QQQ", "2018-06-18"),
            ("QLD_2025_FORM_8937_SPLIT", "QLD", "2023-09-20"),
        ):
            raw = (sid + " fixture bytes").encode()
            relative = "raw/" + sid.lower() + ".txt.gz"
            (base / relative).write_bytes(gzip.compress(raw))
            sources[sid] = {
                "status": "FETCHED_SOURCE_UNCERTIFIED",
                "url": "https://www.sec.gov/Archives/edgar/data/issuer_evidence",
                "body_sha256": sha256(raw).hexdigest(), "raw_archive": relative,
                "anchor_grade_by_claim": {symbol+"|"+day: "BOTH_NEARBY_ANCHORS_OBSERVED"},
            }
        (base / "report.json").write_text(json.dumps({"source_results": sources}))
        records = [
            {"symbol": "QQQ", "ex_date": "2018-06-18", "primary_amount_usd": "0.37837",
             "alpaca_rate": "0.37638"},
            {"symbol": "QLD", "ex_date": "2023-09-20",
             "third_party_raw_2023_cash_usd": "0.176282",
             "third_party_adjusted_cash_usd": "0.088141",
             "split_new_shares_per_old": "2",
             "split_event_date": "2025-11-20"},
        ]
        for record in records:
            record.update(actual_payment_certified="False",
                          independent_adjustment_factor_certified="False",
                          independent_close_certified="False")
        columns = list(dict.fromkeys(k for r in records for k in r))
        with (base / "unresolved_review.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
        return base

    def test_secondary_conflict_is_hold_and_ratio_is_consistent(self):
        with TemporaryDirectory() as d:
            r = audit(self.fixture(d))
            self.assertTrue(r["both_archived_sources_verified"])
            self.assertEqual(r["issuer_payments_certified"], 0)
            self.assertEqual(r["source_finality_verified"], 0)
            qqq, qld = r["events"]
            self.assertEqual(qqq["sec_quote_minus_alpaca_usd"], "0.00199")
            self.assertEqual(qqq["secondary_rounded_minus_alpaca_usd"], "0.00002")
            self.assertTrue(qld["candidate_split_math_consistent"])
            self.assertEqual(qld["split_adjusted_cash_candidate_usd"], "0.088141")
            self.assertTrue(all(e["research_hold"] and not e["actual_payment_certified"]
                                for e in r["events"]))
            self.assertTrue(all(not x["unarchived_research_leads_are_certified"]
                                for x in [r]))

    def test_changed_original_bytes_are_rejected(self):
        with TemporaryDirectory() as d:
            base = self.fixture(d)
            path = base / "raw/qqq_2018_sec_2020_q3_table.txt.gz"
            path.write_bytes(gzip.compress(b"tampered"))
            with self.assertRaisesRegex(ValueError, "SOURCE_BYTES_SHA256_MISMATCH"):
                audit(base)

    def test_missing_original_archive_keeps_hold(self):
        with TemporaryDirectory() as d:
            base = self.fixture(d)
            (base / "raw/qld_2025_form_8937_split.txt.gz").unlink()
            r = audit(base)
            self.assertFalse(r["both_archived_sources_verified"])
            self.assertEqual(r["events"][1]["archived_evidence_status"],
                             "SOURCE_RAW_BYTES_MISSING_HOLD")
            self.assertEqual(r["source_finality_verified"], 0)

    def test_upstream_promotion_not_accepted(self):
        with TemporaryDirectory() as d:
            base = self.fixture(d)
            path = base / "unresolved_review.csv"
            path.write_text(path.read_text().replace("False,False,False", "True,False,False", 1))
            with self.assertRaisesRegex(ValueError, "UPSTREAM_FINALITY_UNEXPECTEDLY_PROMOTED"):
                audit(base)


if __name__ == "__main__":
    unittest.main()
