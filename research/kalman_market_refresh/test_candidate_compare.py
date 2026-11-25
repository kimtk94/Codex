import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pandas as pd

from candidate_compare import KEYS, compare_archives, compare_frames


def frame(start="2026-09-01", periods=30, adjusted=False):
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "timestamp": dates, "is_adjusted": adjusted,
        "symbol": "TEST", "source": "yfinance",
        "open": 100., "high": 102., "low": 98., "close": 101.,
    })


def bundle(path, market, *, tamper=False):
    members = {}
    for key in KEYS:
        members[f"market/raw/yfinance/{key}.parquet"] = market.to_parquet(index=False)
        members[f"features/talib/{key[3:]}.parquet"] = b"fixture feature bytes"
    manifest = {
        "schema": "kalman-daily-market-research-bundle-v1",
        "status": "RESEARCH_ONLY_VALIDATED",
        "production_writes": False,
        "fred_latest_revised_not_vintage_safe": True,
        "market_assets": len(KEYS), "feature_assets": len(KEYS), "fred_series_success": 12,
        "members": [{"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                    for p, b in members.items()],
    }
    readiness = {"production_writes": False, "point_in_time_training_ready": False,
                 "expected_last_completed_nyse_session": "2026-10-30"}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p, data in members.items():
            z.writestr(p, data + b"tampered" if tamper and p == "market/raw/yfinance/yf_spy.parquet" else data)
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("readiness.json", json.dumps(readiness))


class CandidateCompareContracts(unittest.TestCase):
    def test_overlap_same_basis_retains_hold(self):
        old = frame()
        new = frame("2026-09-06", 35)
        r = compare_frames(old, new, "yf_spy")
        self.assertEqual(r["overlap_rows"], 25)
        self.assertEqual(r["new_tail_rows"], 10)
        self.assertEqual(r["original_dates_omitted_before_candidate_start"], 5)
        self.assertEqual(r["overlap_repriced_fields"], 0)
        self.assertTrue(r["adjustment_basis_matches"])
        self.assertEqual(r["release"], "HOLD")

    def test_basis_change_and_price_revision(self):
        old, new = frame(), frame(adjusted=True)
        new.loc[0, "close"] *= 1.01
        r = compare_frames(old, new, "yf_spy")
        self.assertFalse(r["adjustment_basis_matches"])
        self.assertEqual(r["overlap_repriced_fields"], 1)
        self.assertAlmostEqual(r["overlap_max_absolute_revision_bp"], 100.)
        self.assertIn("ADJUSTMENT_BASIS_MISMATCH", r["reason_codes"])

    def test_internal_omission_and_bad_ohlc(self):
        old, new = frame(), frame().drop(index=5)
        new.loc[6, "high"] = 80.
        new.loc[7, "close"] = float("nan")
        r = compare_frames(old, new, "yf_spy")
        self.assertEqual(r["original_dates_omitted_within_or_after_candidate_range"], 1)
        self.assertEqual(r["candidate_inconsistent_ohlc_rows"], 1)
        self.assertEqual(r["candidate_invalid_price_rows"], 1)

    def test_duplicate_dates_and_nonboolean_basis_rejected(self):
        old = frame()
        duplicate = pd.concat([old.iloc[:1], old], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "MARKET_DUPLICATE_DATES"):
            compare_frames(old, duplicate, "yf_spy")
        with self.assertRaisesRegex(ValueError, "MARKET_PRICE_BASIS_UNKNOWN"):
            compare_frames(old, old.assign(is_adjusted="False"), "yf_spy")

    def test_documented_soxx_split_alignment(self):
        old = frame("2026-10-01", 30).assign(symbol="SOXX")
        new = frame("2026-10-01", 55).assign(symbol="SOXX")
        new.loc[:, ["open", "high", "low", "close"]] /= 3
        r = compare_frames(old, new, "yf_soxx", asof="2026-11-24")
        split = r["documented_split_alignment"]
        self.assertEqual(split["overlap_fields_checked"], 120)
        self.assertTrue(split["all_overlap_fields_match_documented_split_within_tolerance"])
        self.assertFalse(split["price_rewritten"])
        self.assertFalse(split["official_regular_close_certified"])
        self.assertEqual(r["release"], "HOLD")
        new.loc[0, "close"] *= 1.01
        r = compare_frames(old, new, "yf_soxx")
        self.assertFalse(r["documented_split_alignment"]["all_overlap_fields_match_documented_split_within_tolerance"])
        self.assertIsNone(compare_frames(old, new, "yf_spy")["documented_split_alignment"])

    def test_split_pattern_never_applies_before_effective_session(self):
        old = frame("2026-09-01", 30).assign(symbol="SOXX")
        new = frame("2026-09-01", 35).assign(symbol="SOXX")
        new.loc[:, ["open", "high", "low", "close"]] /= 3
        self.assertIsNone(compare_frames(old, new, "yf_soxx")["documented_split_alignment"])

    def test_common_asof_dates_excluded_and_quality_dates_retained(self):
        old = frame("2026-10-25", 7)
        new = frame("2026-10-25", 32)
        new.loc[1, "close"] = float("nan")
        new.loc[2, "high"] = 80.
        r = compare_frames(old, new, "yf_usdkrw", asof="2026-11-24")
        self.assertEqual(r["candidate_quality_dates"]["after_common_completed_xnys_asof_dates"], ["2026-11-25"])
        self.assertEqual(r["candidate_tail_rows_after_common_asof"], 1)
        self.assertEqual(r["candidate_tail_rows_at_or_before_common_asof"], 24)
        self.assertEqual(r["candidate_quality_dates"]["invalid_ohlc_dates"], ["2026-10-26"])
        self.assertEqual(r["candidate_quality_dates"]["inconsistent_ohlc_dates"], ["2026-10-27"])

    def test_calendar_proxy_classifies_but_does_not_certify_missing_bars(self):
        old = frame("2026-11-20", 5)
        new = old.copy()
        new.loc[[0, 1], "close"] = float("nan")
        r = compare_frames(old, new, "yf_vix")
        q = r["candidate_quality_dates"]
        self.assertEqual(q["invalid_on_xnys_proxy_dates"], ["2026-11-20"])
        self.assertEqual(q["invalid_off_xnys_proxy_dates"], ["2026-11-21"])
        self.assertTrue(q["xnys_proxy_is_not_provider_calendar_certification"])

    def test_full_archives_metadata_only_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            old, new = Path(root)/"old.zip", Path(root)/"new.zip"
            bundle(old, frame())
            bundle(new, frame("2026-09-06", 35))
            before = old.read_bytes()
            r = compare_archives(old, new)
            self.assertEqual(r["assets_compared"], 19)
            self.assertEqual(r["assets_matching_basis"], 19)
            self.assertEqual(r["candidate_tail_rows_observed"], 190)
            self.assertEqual(r["assets_with_original_dates_omitted"], 19)
            self.assertEqual(r["approved_rows_for_merge"], 0)
            self.assertFalse(r["ready_for_pit_training"])
            self.assertFalse(r["original_drive_zip_replaced"])
            self.assertEqual(old.read_bytes(), before)

    def test_hash_mismatch_rejected_before_price_comparison(self):
        with tempfile.TemporaryDirectory() as root:
            old, new = Path(root)/"old.zip", Path(root)/"new.zip"
            bundle(old, frame())
            bundle(new, frame(), tamper=True)
            with self.assertRaisesRegex(ValueError, "ARCHIVE_MEMBER_HASH_MISMATCH"):
                compare_archives(old, new)


if __name__ == "__main__":
    unittest.main()
