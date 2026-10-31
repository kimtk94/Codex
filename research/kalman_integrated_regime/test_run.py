"""Offline contract tests: fabricated candles only, never presented as backtest evidence."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.run import (
    FEE, build_features, label_events, select_nonoverlap, settle,
)


class RegimeContractTests(unittest.TestCase):
    def test_intra_bar_dual_touch_is_pessimistic(self):
        d = pd.Timestamp("2025-02-03")
        candle = pd.DataFrame([{"open": 100., "high": 105., "low": 95.,
                                "close": 101.}])
        exit_day, price, reason, net = settle([(d, candle)], entry=100.)
        self.assertEqual(exit_day, d)
        self.assertEqual(reason, "SL")
        self.assertAlmostEqual(price, 97.)
        self.assertAlmostEqual(net, 0.97 * (1-FEE)**2 - 1)

    def test_open_gap_filled_at_open(self):
        d = pd.Timestamp("2025-02-03")
        candle = pd.DataFrame([{"open": 95., "high": 100., "low": 90.,
                                "close": 97.}])
        _, price, reason, _ = settle([(d, candle)], entry=100.)
        self.assertEqual(reason, "SL_GAP")
        self.assertEqual(price, 95.)

    def test_market_uses_prior_session_not_same_day(self):
        dates = pd.bdate_range("2024-01-01", periods=60)
        prices = pd.DataFrame({
            "close_qld": np.linspace(10., 16., 60),
            "close_qqq": np.linspace(20., 25., 60)}, index=dates)
        macro = {key: pd.Series(np.linspace(100., 150., 60), index=dates)
                 for key in ("yf_vix", "yf_hyg", "yf_lqd",
                             "yf_tnx", "yf_spy", "yf_smh")}
        base = build_features(prices, macro)
        alt = {k: v.copy() for k, v in macro.items()}
        alt["yf_vix"].loc[dates[45]] = 9999.
        alt["yf_tnx"].loc[dates[45]] = 9999.
        modified = build_features(prices, alt)
        self.assertAlmostEqual(base.loc[dates[45], "vix_lag1"],
                               modified.loc[dates[45], "vix_lag1"])
        self.assertAlmostEqual(base.loc[dates[45], "tnx_lag1"],
                               modified.loc[dates[45], "tnx_lag1"])
        self.assertNotEqual(base.loc[dates[46], "vix_lag1"],
                            modified.loc[dates[46], "vix_lag1"])

    def test_exact_four_sessions_and_nonoverlap(self):
        dates = pd.bdate_range("2025-01-06", periods=7)
        complete = {d: pd.DataFrame([{
            "open": 100., "high": 101., "low": 99., "close": 100.
        }]) for d in dates}
        candidates = label_events(dates, complete)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates.iloc[0].entry_date, dates[1])
        self.assertEqual(candidates.iloc[0].exit_date, dates[4])
        filtered = select_nonoverlap(candidates)
        self.assertEqual(len(filtered), 1)


if __name__ == "__main__":
    unittest.main()
