"""Daily20 price variance queue tests: diagnostic prioritization, never finality."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from price_basis_bridge import compare
from price_variance_triage import BUCKETS, build, classify, csv_payload
from test_price_basis_bridge import fake_reports, SPEC, SESSION


def fixture(root, *, factor_coverage=25):
    src, venue, factor = fake_reports(root, factor_coverage=factor_coverage)
    bridge = compare(SPEC, src, venue, factor, root)
    return bridge


def grade(bridge):
    blob = json.dumps(bridge, sort_keys=True).encode()
    return build(SPEC, bridge, bridge_sha256=sha256(blob).hexdigest())


class VarianceTriageTests(unittest.TestCase):
    def test_complete_25_equities_1_vix_always_hold(self):
        with TemporaryDirectory() as d:
            result = grade(fixture(Path(d)))
            self.assertEqual(result["equity_etf_cases"], 25)
            self.assertEqual(result["vix_index_separate"], 1)
            self.assertEqual(result["primary_M_research_references"], 25)
            self.assertEqual(result["yahoo_unrepaired_traces"], 25)
            self.assertEqual(result["bucket_counts"][BUCKETS[3]], 25)
            self.assertEqual(len(result["top_10_abs_bps"]), 10)
            self.assertEqual(len(result["review_queue"]), 25)
            self.assertEqual(result["independent_final_close_certified"], 0)
            self.assertEqual(result["independent_factor_certified"], 0)
            self.assertTrue(all(not x["likely_cause_certified"] and
                                not x["finality_verified"]
                                for x in result["review_queue"]))
            self.assertEqual(result["status"], "RAW_VS_SPLIT_ADJUSTED_DIAGNOSTIC_HOLD")
            self.assertFalse(result["strategy_promoted"])

    def test_thresholds_apply_to_research_priority_only(self):
        observations = [
            (100.004, 100.0, BUCKETS[0]),
            (100.02, 100.0, BUCKETS[1]),
            (100.20, 100.0, BUCKETS[2]),
            (101.0, 100.0, BUCKETS[3]),
            (None, 100.0, BUCKETS[4]),
        ]
        for raw, split, expected in observations:
            bucket, priority = classify(raw, split)
            self.assertEqual(bucket, expected)
            self.assertTrue(priority.startswith("P"))
        self.assertEqual(classify(100.0, 100.0)[0], BUCKETS[0])

    def test_relative_bps_signed_and_sort_stable(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            spy = next(x for x in bridge["rows"] if x["symbol"] == "SPY")
            spy["raw_primary_M_auction_price"] = 99.0
            result = grade(bridge)
            row = next(x for x in result["review_queue"] if x["symbol"] == "SPY")
            self.assertLess(row["raw_minus_yahoo_split_bps"], 0)
            self.assertEqual(row["raw_minus_yahoo_split_usd"], -1)
            self.assertFalse(row["likely_cause_certified"])

    def test_vendor_trace_missing_not_substituted_with_model(self):
        with TemporaryDirectory() as d:
            result = grade(fixture(Path(d), factor_coverage=24))
            self.assertEqual(result["yahoo_unrepaired_traces"], 24)
            self.assertEqual(result["bucket_counts"][BUCKETS[4]], 1)
            row = next(x for x in result["review_queue"]
                       if x["classification"] == BUCKETS[4])
            self.assertIsNone(row["raw_minus_yahoo_split_bps"])
            self.assertEqual(row["review_priority"], "P0_MISSING_INPUT")

    def test_missing_raw_reference_is_not_inferred_from_vendor(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["rows"][0]["raw_primary_M_auction_price"] = None
            bridge["rows"][0]["raw_reference_provenance"] = None
            bridge["raw_primary_M_auction_reference_count"] = 24
            result = grade(bridge)
            self.assertEqual(result["primary_M_research_references"], 24)
            self.assertEqual(result["bucket_counts"][BUCKETS[4]], 1)
            self.assertEqual(result["independent_final_close_certified"], 0)

    def test_malformed_exchange_provenance_is_rejected(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["rows"][0]["raw_reference_provenance"]["provider"] = "Untrusted"
            with self.assertRaisesRegex(ValueError, "PROVENANCE_INCOMPLETE"):
                grade(bridge)

    def test_missing_parquet_sha256_is_rejected(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["rows"][0]["model_parquet_sha256"] = None
            with self.assertRaisesRegex(ValueError, "PARQUET_SHA256_MISSING"):
                grade(bridge)

    def test_vendor_ratio_change_is_not_acceptably_reused(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["rows"][0]["vendor_unrepaired_adj_over_close"] = 0.12
            with self.assertRaisesRegex(ValueError, "VENDOR_RATIO_MISMATCH"):
                grade(bridge)

    def test_source_lying_about_certification_is_rejected(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["research_price_certified"] = 25
            with self.assertRaisesRegex(ValueError, "FALSE_CERTIFICATION"):
                grade(bridge)

    def test_mismatch_counts_must_reconcile_bridge(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["same_session_model_vendor_adj_close_mismatches_gt_half_cent"] = 3
            with self.assertRaisesRegex(ValueError, "MODEL_DIFFERENCE_DIVERGED"):
                grade(bridge)

    def test_vix_is_not_falsely_treated_as_stock(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            vix = next(x for x in bridge["rows"] if x["symbol"] == "^VIX")
            vix["vendor_unrepaired_adj_over_close"] = 1.0
            with self.assertRaisesRegex(ValueError, "VIX_SHOULD_NOT_HAVE_STOCK_FACTOR"):
                grade(bridge)

    def test_no_duplicate_or_missing_symbol_allowed(self):
        with TemporaryDirectory() as d:
            bridge = fixture(Path(d))
            bridge["rows"][1] = dict(bridge["rows"][0])
            with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_UNKNOWN_SYMBOL"):
                grade(bridge)

    def test_csv_reproducible_and_25_records(self):
        with TemporaryDirectory() as d:
            result = grade(fixture(Path(d)))
            a = csv_payload(result["review_queue"])
            b = csv_payload(result["review_queue"])
            self.assertEqual(a, b)
            self.assertEqual(len(a.decode().splitlines()), 26)
            self.assertIn("research", result["strict_interpretation"].lower())
            self.assertEqual(len(result["source_bridge_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
