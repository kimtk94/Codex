from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from engine.features_v2.talib_features import build_talib_features, compare_legacy_rsi
from engine.screeners.finviz_snapshot import (
    FinvizSettings,
    build_candidate_universe,
    merge_views,
)


class ExtendedMarketToolsV2Tests(unittest.TestCase):
    def test_talib_feature_shape_and_legacy_rsi_comparison(self) -> None:
        n = 120
        idx = pd.date_range("2026-01-01", periods=n, freq="D")
        close = pd.Series(np.linspace(100, 130, n) + np.sin(np.arange(n) / 3), index=idx)
        frame = pd.DataFrame(
            {
                "timestamp": idx,
                "symbol": "TEST",
                "open": close.values - 0.2,
                "high": close.values + 1.0,
                "low": close.values - 1.0,
                "close": close.values,
                "adj_close": close.values,
                "volume": np.linspace(1000, 2000, n),
            }
        )

        features = build_talib_features(frame)
        expected = {
            "talib_v2_rsi14",
            "talib_v2_macd",
            "talib_v2_adx14",
            "talib_v2_atr14",
            "talib_v2_roc10",
            "talib_v2_obv",
            "talib_v2_bb_pctb",
        }
        self.assertTrue(expected.issubset(features.columns))
        self.assertEqual(len(features), n)

        comparison = compare_legacy_rsi(frame, features)
        self.assertEqual(comparison["status"], "READY")
        self.assertGreater(comparison["overlap_rows"], 50)
        self.assertIsNotNone(comparison["correlation"])

    def test_finviz_merge_and_local_candidate_filter(self) -> None:
        overview = pd.DataFrame(
            {
                "Ticker": ["AAA", "BBB"],
                "Market Cap": ["10B", "500M"],
                "Price": [100.0, 4.0],
                "Volume": [2_000_000, 100_000],
                "Sector": ["Technology", "Energy"],
                "Industry": ["Software", "Oil"],
                "snapshot_at": ["2026-09-11T08:00:00+09:00"] * 2,
            }
        )
        technical = pd.DataFrame(
            {
                "Ticker": ["AAA", "BBB"],
                "RSI": [55.0, 75.0],
                "Rel Volume": [1.2, 0.8],
                "SMA20": [0.05, -0.10],
                "SMA50": [0.10, -0.20],
                "SMA200": [0.20, -0.30],
                "snapshot_at": ["2026-09-11T08:00:00+09:00"] * 2,
            }
        )
        merged = merge_views({"overview": overview, "technical": technical})
        settings = FinvizSettings(
            output_dir=pd.Path if False else __import__("pathlib").Path("/tmp/unused"),
            min_price=5,
            min_market_cap=1_000_000_000,
            min_volume=500_000,
        )
        candidates = build_candidate_universe(merged, settings)
        passes = candidates.set_index("ticker")["passes_local_filter"].to_dict()
        self.assertTrue(passes["AAA"])
        self.assertFalse(passes["BBB"])


if __name__ == "__main__":
    unittest.main()
