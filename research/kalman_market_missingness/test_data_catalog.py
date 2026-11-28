import copy
import unittest

from backfill_queue import DAILY_ID, MACRO_ID, EXPECTED_FRED, PAIRED_SHARED, VERSION
from data_catalog import build_catalog, WIDE_ONLY


def plan():
    market = []
    for key in sorted(PAIRED_SHARED | WIDE_ONLY):
        shared = key in PAIRED_SHARED
        market.append({
            "indicator": key, "source_last": "2026-10-30",
            "target_last": "2026-11-20", "frequency": "XNYS",
            "point_in_time_source_verified": False,
            "independent_official_close_verified": False,
            "can_modify_historical_archive": False,
            "expected_tail_rows": 15, "candidate_tail_rows": 15 if shared else 0,
            "candidate_missing_expected_rows": 0 if shared else 15,
            "adjustment_flag_matches": True if shared else None,
            "reuse_status": "UNAPPROVED_SAME_PROVIDER_CANDIDATE_ONLY" if shared
                            else "NOT_AVAILABLE_IN_DAILY20",
        })
    fred = [{
        "series_id": key, "last_observed": "2026-10-30",
        "date_asof_research_target": "2026-11-20",
        "source_record_revision": "LATEST_REVISED_NOT_ALFRED_PIT",
        "fill_null_with_forward_data": False,
        "point_in_time_training_eligible": False,
        "archive_can_be_replaced": False,
    } for key in EXPECTED_FRED]
    return {
        "version": VERSION, "status": "BACKFILL_CANDIDATES_STAGED_METADATA_ONLY_RESEARCH_HOLD",
        "research_only": True, "archive_integrity_sha256_pass": True,
        "fred_latest_revised_not_pit": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "source_bars_modified": False, "original_drive_zip_overwritten": False,
        "automatically_merged": False, "daily20_first_seal_touched": False,
        "new_prospective_signals_created": 0,
        "source_archive_drive_id": MACRO_ID, "reference_archive_drive_id": DAILY_ID,
        "source_archive_sha256": "a"*64, "reference_archive_sha256": "b"*64,
        "source_last_completed_xnys": "2026-10-30",
        "reference_last_completed_xnys": "2026-11-20",
        "market_assets": 19, "overlapping_same_vendor_assets": 9,
        "market_only_assets_need_new_collection": 10,
        "fred_series_require_republication_check": 12,
        "feature_assets_need_recalculation_after_approved_source": 19,
        "market_expected_tail_rows_total": 285,
        "same_vendor_candidate_tail_rows": 135,
        "candidate_missing_expected_tail_rows": 150,
        "market_assets_with_any_reusable_candidate": 9,
        "market_queue": market, "fred_queue": fred,
    }


class CatalogTests(unittest.TestCase):
    def test_complete_metadata_inventory(self):
        p = plan()
        original = copy.deepcopy(p)
        r = build_catalog(p)
        self.assertEqual(p, original)
        self.assertEqual(len(r["datasets"]), 50)
        self.assertEqual(len({(x["layer"], x["dataset"]) for x in r["datasets"]}), 50)
        self.assertEqual((r["candidate_tail_rows"], r["missing_tail_rows"]), (135, 150))
        self.assertEqual(r["approved_backfill_rows"], 0)
        self.assertFalse(any(x["pit_approved"] or x["canonical_write_allowed"]
                             for x in r["datasets"]))
        self.assertEqual(r["reference_archive"]["raw_assets"], 26)
        self.assertTrue(all(x["last_observed"] is None for x in r["datasets"]
                            if x["layer"] == "FEATURE"))

    def test_adjustment_basis_mismatch_remains_hold(self):
        p = plan()
        item = next(r for r in p["market_queue"] if r["indicator"] in PAIRED_SHARED)
        item["adjustment_flag_matches"] = False
        item["reuse_status"] = "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD"
        r = build_catalog(p)
        self.assertEqual(next(x["state"] for x in r["datasets"]
                              if x["dataset"] == item["indicator"] and x["layer"] == "MARKET"),
                         "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD")

    def test_unverified_or_promoted_plan_rejected(self):
        for key, value in (("archive_integrity_sha256_pass", False),
                           ("production_writes", True), ("new_prospective_signals_created", 1),
                           ("fred_latest_revised_not_pit", False),
                           ("reference_archive_sha256", "bad")):
            p = plan()
            p[key] = value
            with self.assertRaises(ValueError):
                build_catalog(p)

    def test_duplicate_or_missing_dataset_rejected(self):
        p = plan()
        p["market_queue"][-1] = p["market_queue"][0]
        with self.assertRaisesRegex(ValueError, "QUEUE_UNIVERSE"):
            build_catalog(p)

    def test_false_tail_total_and_external_candidate_rejected(self):
        p = plan()
        p["same_vendor_candidate_tail_rows"] += 1
        with self.assertRaisesRegex(ValueError, "SUMMARY_ACCOUNTING"):
            build_catalog(p)
        p = plan()
        r = next(x for x in p["market_queue"] if x["indicator"] in WIDE_ONLY)
        r["candidate_tail_rows"] = 1
        r["candidate_missing_expected_rows"] = 14
        with self.assertRaisesRegex(ValueError, "MARKET_EXTERNAL_SOURCE"):
            build_catalog(p)

    def test_fred_pit_and_market_write_rejected(self):
        p = plan()
        p["fred_queue"][0]["point_in_time_training_eligible"] = True
        with self.assertRaisesRegex(ValueError, "FRED_UNSAFE"):
            build_catalog(p)
        p = plan()
        p["market_queue"][0]["can_modify_historical_archive"] = True
        with self.assertRaisesRegex(ValueError, "MARKET_UNSAFE"):
            build_catalog(p)


if __name__ == "__main__":
    unittest.main()
