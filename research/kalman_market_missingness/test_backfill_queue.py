"""Synthetic original/new archive contrast: never creates certified market prices."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import unittest

import pandas as pd

from fetch_private_zip import APPROVED_READONLY_ARCHIVES

from backfill_queue import (
    EXPECTED_FRED, PAIRED_SHARED, VERSION, validated_archives,
    shared_candidate, make_plan,
)

OLD_KEYS = sorted(PAIRED_SHARED | {
    "yf_btc", "yf_dia", "yf_dxy", "yf_ixic", "yf_kosdaq", "yf_kospi",
    "yf_soxx", "yf_sp500", "yf_tnx", "yf_usdkrw",
})
NEW_KEYS = sorted(PAIRED_SHARED | {f"yf_dummy{i:02d}" for i in range(17)})


def bars(dates, key):
    # Research-only synthetic candles; ALWAYS labeled fixtures.
    values = [100.0 + 0.09 * i for i in range(len(dates))]
    return pd.DataFrame({
        "timestamp": pd.DatetimeIndex(dates, tz="UTC"),
        "market": "SYNTHETIC_NOT_MARKET",
        "symbol": key,
        "open": values,
        "high": [x + 1 for x in values],
        "low": [x - 1 for x in values],
        "close": values,
        "volume": [1234] * len(dates),
        "is_adjusted": [key != "yf_vix"] * len(dates),
    })


def parquet(df):
    out = BytesIO()
    df.to_parquet(out, index=False)
    return out.getvalue()


def bundle(objects):
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as z:
        for name, body in objects.items():
            z.writestr(name, body)
    return buf.getvalue()


def fixtures():
    old_days = pd.bdate_range("2026-10-01", "2026-10-30")
    new_days = pd.bdate_range("2026-10-01", "2026-11-20")
    m = {}
    for key in OLD_KEYS:
        # The actual wide-market ZIP already includes Saturday Oct 31
        # BTC / USDKRW stamped observations despite its XNYS as-of Oct 30.
        per_asset_days = old_days
        if key in ("yf_btc", "yf_usdkrw"):
            per_asset_days = old_days.append(
                pd.DatetimeIndex(["2026-10-31"]))
        m[f"market/raw/yfinance/{key}.parquet"] = parquet(
            bars(per_asset_days, key))
    for key in OLD_KEYS:
        m[f"features/talib/{key.removeprefix('yf_')}.parquet"] = b"SYNTHETIC_DERIVED_FEATURE_NOT_REAL"
    m["fred/fred_status.json"] = json.dumps({
        "source_revision": "latest_revised",
        "point_in_time_vintage": False,
        "series": {key: {"last_observation": "2026-10-29"}
                   for key in EXPECTED_FRED},
    }).encode()
    m["fred/fred_latest_revised_long.csv"] = b"series_id,observation_date,value\n"
    manifest = {
        "schema": "kalman-daily-market-research-bundle-v1",
        "status": "RESEARCH_ONLY_VALIDATED",
        "production_writes": False,
        "market_assets": 19,
        "feature_assets": 19,
        "fred_series_success": 12,
        "fred_latest_revised_not_vintage_safe": True,
        "members": [{"path": key, "sha256": sha256(v).hexdigest()}
                    for key, v in sorted(m.items())],
    }
    m["manifest.json"] = json.dumps(manifest).encode()
    m["readiness.json"] = json.dumps({
        "expected_last_completed_nyse_session": "2026-10-30",
        "point_in_time_training_ready": False,
        "production_writes": False,
    }).encode()
    d = {}
    for key in NEW_KEYS:
        d[f"market/raw/yfinance/{key}.parquet"] = parquet(bars(new_days, key))
        d[f"features/talib/{key.removeprefix('yf_')}.parquet"] = b"TEST_FEATURE"
    d["drive_manifest.json"] = json.dumps({
        "format": "kalman-daily20-drive-v1",
        "research_only": True,
        "production_writes": False,
        "raw_symbols": 26,
        "feature_symbols": 26,
        "data_expected_last_closed_xnys": "2026-11-20",
        "payload_hashes_sha256": {
            key: sha256(v).hexdigest() for key, v in d.items()},
    }).encode()
    return bundle(m), bundle(d)


def replace_member(archive, key, body):
    with ZipFile(BytesIO(archive)) as z:
        objects = {n: z.read(n) for n in z.namelist()}
    objects[key] = body
    return bundle(objects)


class ArchiveBackfillProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = fixtures()

    def test_both_sources_have_40_and_52_valid_checksums(self):
        mzip, dzip, mm, mr, dm, old, new = validated_archives(
            self.old, self.new)
        with mzip, dzip:
            self.assertEqual(len(mm["members"]), 40)
            self.assertEqual(len(dm["payload_hashes_sha256"]), 52)
            self.assertEqual(len(old), 19)
            self.assertEqual(len(new), 26)

    def test_candidate_queue_9_shared_10_external_12_latest_fred(self):
        plan = make_plan(self.old, self.new)
        self.assertEqual(plan["version"], VERSION)
        self.assertEqual(plan["overlapping_same_vendor_assets"], 9)
        self.assertEqual(plan["market_only_assets_need_new_collection"], 10)
        self.assertEqual(plan["fred_series_require_republication_check"], 12)
        self.assertEqual(plan["feature_assets_need_recalculation_after_approved_source"], 19)
        self.assertEqual(plan["candidate_missing_expected_tail_rows"], 0 + sum(
            r["expected_tail_rows"] for r in plan["market_queue"]
            if r["indicator"] not in PAIRED_SHARED))
        self.assertEqual(plan["same_vendor_candidate_tail_rows"], 9 * 15)
        self.assertEqual(plan["candidate_missing_expected_tail_rows"], 155)
        self.assertEqual(plan["market_expected_tail_rows_total"], 290)
        self.assertEqual(plan["market_assets_with_any_reusable_candidate"], 9)
        self.assertFalse(plan["automatically_merged"])
        self.assertFalse(plan["original_drive_zip_overwritten"])
        self.assertFalse(plan["daily20_first_seal_touched"])

    def test_nonshared_btc_requires_collection_not_fake_weekend_prices(self):
        plan = make_plan(self.old, self.new)
        btc = next(r for r in plan["market_queue"] if r["indicator"] == "yf_btc")
        self.assertEqual(btc["reuse_status"], "NOT_AVAILABLE_IN_DAILY20")
        self.assertEqual(btc["frequency"], "calendar")
        self.assertEqual(btc["expected_tail_rows"], 20)
        self.assertEqual(btc["source_last"], "2026-10-31")
        self.assertEqual(btc["candidate_tail_rows"], 0)

    def test_both_revised_latest_fred_and_features_research_hold(self):
        plan = make_plan(self.old, self.new)
        self.assertTrue(plan["fred_latest_revised_not_pit"])
        self.assertEqual(len(plan["fred_queue"]), 12)
        for f in plan["fred_queue"]:
            self.assertFalse(f["point_in_time_training_eligible"])
            self.assertFalse(f["fill_null_with_forward_data"])

    def test_explicit_adjusted_basis_mismatch_is_never_certified(self):
        old = bars(pd.bdate_range("2026-10-01", "2026-10-30"), "yf_spy")
        new = bars(pd.bdate_range("2026-10-01", "2026-11-20"), "yf_spy")
        new["is_adjusted"] = False
        r = shared_candidate(old, new, key="yf_spy",
                             source_day="2026-10-30", target_day="2026-11-20")
        self.assertFalse(r["adjustment_flag_matches"])
        self.assertEqual(r["reuse_status"], "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD")

    def test_fetcher_can_only_read_two_approved_archives(self):
        self.assertEqual(set(APPROVED_READONLY_ARCHIVES), {
            "1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd",
            "1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE",
        })
        self.assertTrue(all(name.endswith(".zip")
                            for name, _ in APPROVED_READONLY_ARCHIVES.values()))

    def test_same_provider_price_revision_kept_as_evidence_not_overwritten(self):
        old = bars(pd.bdate_range("2026-10-01", "2026-10-30"), "yf_qqq")
        new = bars(pd.bdate_range("2026-10-01", "2026-11-20"), "yf_qqq")
        new.loc[new.index[1], "close"] *= 1.02
        r = shared_candidate(old, new, key="yf_qqq",
                             source_day="2026-10-30", target_day="2026-11-20")
        self.assertGreater(r["overlap_ohlc_repriced_fields"], 0)
        self.assertGreater(r["overlap_max_absolute_revision_bp"], 100)
        self.assertFalse(r["independent_official_close_verified"])
        self.assertFalse(r["can_modify_historical_archive"])

    def test_incomplete_new_tail_refused_for_shared_stock(self):
        old = bars(pd.bdate_range("2026-10-01", "2026-10-30"), "yf_spy")
        new = bars(pd.bdate_range("2026-10-01", "2026-11-20"), "yf_spy")
        new = new[new.timestamp.dt.strftime("%Y-%m-%d") != "2026-11-19"]
        with self.assertRaisesRegex(ValueError, "CANDIDATE_MISSING_REQUIRED_TAIL"):
            shared_candidate(old, new, key="yf_spy",
                             source_day="2026-10-30", target_day="2026-11-20")

    def test_duplicate_timestamp_rejected_before_merging(self):
        old = bars(pd.bdate_range("2026-10-01", "2026-10-30"), "yf_spy")
        new = bars(pd.bdate_range("2026-10-01", "2026-11-20"), "yf_spy")
        new.iloc[-1, new.columns.get_loc("timestamp")] = new.iloc[-2].timestamp
        with self.assertRaisesRegex(ValueError, "MARKET_BAD_DATES"):
            shared_candidate(old, new, key="yf_spy",
                             source_day="2026-10-30", target_day="2026-11-20")

    def test_forged_macro_price_member_hash_rejected(self):
        name = "market/raw/yfinance/yf_qqq.parquet"
        source = replace_member(self.old, name, b"FABRICATED_SOURCE")
        with self.assertRaisesRegex(ValueError, "MACRO_SHA256_MISMATCH"):
            validated_archives(source, self.new)

    def test_forged_daily20_price_member_hash_rejected(self):
        name = "market/raw/yfinance/yf_spy.parquet"
        source = replace_member(self.new, name, b"FABRICATED_SOURCE")
        with self.assertRaisesRegex(ValueError, "DAILY20_SHA256_MISMATCH"):
            validated_archives(self.old, source)

    def test_future_macro_archive_rejected(self):
        with ZipFile(BytesIO(self.old)) as z:
            objects = {n: z.read(n) for n in z.namelist()}
        r = json.loads(objects["readiness.json"])
        r["expected_last_completed_nyse_session"] = "2026-11-25"
        objects["readiness.json"] = json.dumps(r).encode()
        with self.assertRaisesRegex(ValueError, "ARCHIVE_SESSIONS_INVALID"):
            validated_archives(bundle(objects), self.new)

    def test_fake_point_in_time_macro_claim_rejected(self):
        with ZipFile(BytesIO(self.old)) as z:
            objects = {n: z.read(n) for n in z.namelist()}
        r = json.loads(objects["readiness.json"])
        r["point_in_time_training_ready"] = True
        objects["readiness.json"] = json.dumps(r).encode()
        with self.assertRaisesRegex(ValueError, "MACRO_POINT_IN_TIME_MISREPRESENTED"):
            validated_archives(bundle(objects), self.new)

    def test_malformed_archive_member_path_rejected(self):
        with ZipFile(BytesIO(self.old)) as z:
            objects = {n: z.read(n) for n in z.namelist()}
        objects["../source_escape.txt"] = b"BAD"
        with self.assertRaisesRegex(ValueError, "UNSAFE_ARCHIVE_MEMBER"):
            validated_archives(bundle(objects), self.new)


    def test_release_decision_is_hold_even_when_all_shared_tails_exist(self):
        plan = make_plan(self.old, self.new)
        d = plan["release_decision"]
        self.assertEqual(d["decision"], "HOLD")
        self.assertEqual(d["same_provider_available_asset_count"], 9)
        self.assertEqual(d["same_provider_available_candidate_rows"], 135)
        self.assertEqual(d["matching_adjustment_flag_but_uncertified_asset_count"], 9)
        self.assertEqual(d["incompatible_price_basis_asset_count"], 0)
        self.assertEqual(d["market_only_assets_to_refetch"], 10)
        self.assertEqual(d["unfilled_market_tail_rows"], 155)
        self.assertEqual(d["fred_series_blocked_for_pit_training"], 12)
        self.assertEqual(d["approved_market_assets_for_merge"], 0)
        self.assertEqual(d["approved_candidate_rows_for_merge"], 0)
        self.assertEqual(d["independently_certified_regular_closes"], 0)
        self.assertFalse(d["ready_for_pit_training"])
        self.assertFalse(d["ready_to_replace_original_drive_zip"])
        self.assertFalse(d["new_versioned_candidate_archive_created"])
        self.assertFalse(d["daily20_first_seal_touched"])
        self.assertTrue(d["requires_separate_source_qc_and_manual_promotion"])

    def test_release_decision_counts_mismatched_basis_but_never_approves(self):
        # Re-sign a synthetic fixture's original manifest ONLY to isolate
        # semantic rejection from the separate invalid-SHA test.
        name = "market/raw/yfinance/yf_qqq.parquet"
        with ZipFile(BytesIO(self.new)) as z:
            data = {key: z.read(key) for key in z.namelist()}
        prices = pd.read_parquet(BytesIO(data[name]))
        prices["is_adjusted"] = False
        data[name] = parquet(prices)
        manifest = json.loads(data["drive_manifest.json"])
        manifest["payload_hashes_sha256"][name] = sha256(data[name]).hexdigest()
        data["drive_manifest.json"] = json.dumps(manifest).encode()
        plan = make_plan(self.old, bundle(data))
        d = plan["release_decision"]
        self.assertEqual(d["incompatible_price_basis_asset_count"], 1)
        self.assertEqual(d["matching_adjustment_flag_but_uncertified_asset_count"], 8)
        self.assertIn("PRICE_ADJUSTMENT_BASIS_MISMATCH", d["reason_codes"])
        self.assertEqual(d["approved_candidate_rows_for_merge"], 0)
        self.assertEqual(d["decision"], "HOLD")

    def test_cli_writes_valid_read_only_decision_json(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from backfill_queue import main
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "old.zip").write_bytes(self.old)
            (folder / "new.zip").write_bytes(self.new)
            with patch("sys.argv", [
                "backfill_queue.py", "--market-zip", str(folder / "old.zip"),
                "--daily20-zip", str(folder / "new.zip"),
                "--out", str(folder / "out")
            ]):
                self.assertEqual(main(), 0)
            report = json.loads(
                (folder / "out/backfill_decision.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["decision"], "HOLD")
            self.assertFalse(report["ready_to_replace_original_drive_zip"])
            self.assertTrue((folder / "out/backfill_market_queue.csv").exists())


if __name__ == "__main__":
    unittest.main()
