"""Offline falsification: historical recovery must not become a prospective signal."""
import unittest
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd

from historical_backfill_evidence import check_backfill_request, check_target, verify_backfill
from daily20 import market_file, feature_file


class HistoricalBackfillContractTests(unittest.TestCase):
    def test_completed_real_session_allowed(self):
        self.assertEqual(check_target("2026-11-23", asof=date(2026, 11, 24)),
                         date(2026, 11, 23))

    def test_weekend_and_future_rejected(self):
        with self.assertRaisesRegex(ValueError, "TARGET_NOT_XNYS_SESSION"):
            check_target("2026-11-22", asof=date(2026, 11, 24))
        with self.assertRaisesRegex(ValueError, "TARGET_NOT_FULLY_COMPLETED"):
            check_target("2026-11-25", asof=date(2026, 11, 24))
        with self.assertRaisesRegex(ValueError, "TARGET_SESSION_NOT_ISO_DATE"):
            check_target("Nov 23 2026", asof=date(2026, 11, 24))

    def test_one_time_gitops_request_is_research_only(self):
        request = Path('research/kalman_daily20/backfill_requests/2026-11-23.json')
        if not request.exists():
            request = Path('backfill_requests/2026-11-23.json')
        self.assertEqual(check_backfill_request(request, asof=date(2026, 11, 24)),
                         date(2026, 11, 23))
        with TemporaryDirectory() as tmp:
            invalid = Path(tmp) / '2026-11-23.json'
            invalid.write_text('{"version":"kalman-historical-backfill-request-v1",'
                               '"session":"2026-11-23",'
                               '"classification":"RETROSPECTIVE_BACKFILL_NOT_PROSPECTIVE",'
                               '"research_only":true,"production_writes":false,'
                               '"forward_events_created":20,"live_execution":false}')
            with self.assertRaisesRegex(ValueError, "INVALID_RETROSPECTIVE_GITOPS_REQUEST"):
                check_backfill_request(invalid, asof=date(2026, 11, 24))

    def test_all_26_verified_never_forward(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            market, features = root / "market", root / "features"
            symbols = [f"EX{i:02}" for i in range(26)]
            for symbol in symbols:
                sessions = pd.bdate_range(end="2026-11-23", periods=260)
                rows = pd.DataFrame({
                    "timestamp": sessions,
                    "open": 11., "high": 12.,
                    "low": 10., "close": 11.5,
                    "volume": 110,
                })
                raw = market_file(market, symbol)
                raw.parent.mkdir(parents=True, exist_ok=True)
                rows.to_parquet(raw, index=False)
                feat = feature_file(features, symbol)
                feat.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({"timestamp": sessions,
                              "talib_v2_rsi14": 52.}).to_parquet(feat, index=False)
            universe = {"research_only": True, "assets": [
                {"provider_symbol": symbol} for symbol in symbols]}
            out = verify_backfill(universe, market, features,
                                  "2026-11-23", asof=date(2026, 11, 24))
            self.assertEqual(out["status"], "DATA_BACKFILL_VERIFIED")
            self.assertEqual(out["assets_verified"], 26)
            self.assertEqual(out["forward_events_created"], 0)
            self.assertFalse(out["prospective_first_seal"])
            self.assertEqual(out["classification"],
                             "RETROSPECTIVE_BACKFILL_NOT_PROSPECTIVE")

            # Missing or stale features must fail closed, not pass partial archive.
            feature_file(features, symbols[0]).unlink()
            bad = verify_backfill(universe, market, features,
                                  "2026-11-23", asof=date(2026, 11, 24))
            self.assertEqual(bad["status"], "DATA_BACKFILL_HOLD")
            self.assertEqual(bad["assets_verified"], 25)

            # A same-length feature file with divergent trading dates is unsafe.
            altered = pd.DataFrame({"timestamp": sessions,
                                    "talib_v2_rsi14": 52.})
            altered.loc[40, "timestamp"] = pd.Timestamp("2020-01-02")
            altered.to_parquet(feature_file(features, symbols[0]), index=False)
            mismatch = verify_backfill(universe, market, features,
                                       "2026-11-23", asof=date(2026, 11, 24))
            self.assertEqual(mismatch["status"], "DATA_BACKFILL_HOLD")
            self.assertEqual(mismatch["assets_verified"], 25)
            self.assertIn("PRICE_FEATURE_DATES_MISMATCH",
                          mismatch["errors"][0]["error"])

    def test_duplicate_universe_rejected(self):
        universe = {"research_only": True, "assets": [
            {"provider_symbol": "SPY"} for _ in range(26)]}
        with self.assertRaisesRegex(ValueError, "BACKFILL_DUPLICATE_SYMBOLS"):
            verify_backfill(universe, ".", ".", "2026-11-23",
                            asof=date(2026, 11, 24))


if __name__ == "__main__":
    unittest.main()
