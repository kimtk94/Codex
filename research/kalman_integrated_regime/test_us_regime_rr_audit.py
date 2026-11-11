"""Causal regime labels, planned R:R, conditional outcomes and missing-support guards."""
import unittest

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_regime_rr_audit import (
    ex_ante_reward_risk, spy_market_states, trade_group_stats, audited_cohort,
)


class RegimeRiskRewardContracts(unittest.TestCase):
    def test_planned_rr_is_net_of_roundtrip_friction(self):
        result = ex_ante_reward_risk(tp=.03, sl=.03, side_cost=.0015)
        self.assertAlmostEqual(result["planned_win_net_fraction"], .027)
        self.assertAlmostEqual(result["planned_stop_loss_net_fraction"], .033)
        self.assertAlmostEqual(result["planned_reward_to_risk"], 27 / 33, places=6)
        self.assertAlmostEqual(result["simple_barrier_breakeven_win_fraction"], .55)
        with self.assertRaises(ValueError):
            ex_ante_reward_risk(tp=.002, sl=.03, side_cost=.0015)

    def test_market_regime_uses_no_future_dates_or_trade_returns(self):
        dates = pd.bdate_range("2024-01-02", periods=190)
        closes = np.linspace(100., 150., len(dates))
        mock = pd.DataFrame({
            "date_ny": dates,
            "rth_close": closes,
            "complete_rth": True,
        })
        a = spy_market_states(mock)
        self.assertEqual(a.loc[85, "market_state"], "BULL")
        self.assertIn(a.loc[140, "market_volatility_state"], ("HIGH", "LOW"))
        modified = mock.copy()
        modified.loc[151:, "rth_close"] = np.linspace(150., 30., len(mock)-151)
        b = spy_market_states(modified)
        self.assertEqual(a.market_state[:151].tolist(), b.market_state[:151].tolist())
        self.assertEqual(a.market_volatility_state[:151].tolist(),
                         b.market_volatility_state[:151].tolist())
        self.assertEqual(a.loc[0, "market_state"], "UNAVAILABLE")

    def test_bear_state_for_consistent_past_decline(self):
        dates = pd.bdate_range("2024-01-02", periods=190)
        mock = pd.DataFrame({
            "date_ny": dates,
            "rth_close": np.linspace(150., 90., len(dates)),
            "complete_rth": True,
        })
        a = spy_market_states(mock)
        self.assertEqual(a.loc[95, "market_state"], "BEAR")

    def test_realized_r_includes_stop_gap_and_time_close(self):
        rr = ex_ante_reward_risk()
        trades = [
            {"net_return": .027, "trading_sessions_held": 1, "exit_reason": "TAKE"},
            {"net_return": -.053, "trading_sessions_held": 2, "exit_reason": "STOP_GAP"},
            {"net_return": .003, "trading_sessions_held": 4, "exit_reason": "TIME_CLOSE"},
        ]
        r = trade_group_stats(trades, rr["planned_stop_loss_net_fraction"])
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["status"], "INSUFFICIENT_SAMPLE")
        self.assertAlmostEqual(r["expectancy_R"], (.027-.053+.003)/.033/3, places=6)
        self.assertLess(r["worst_realized_R"], -1.)
        self.assertEqual(r["exit_reasons"]["STOP_GAP"], 1)
        self.assertTrue(r["trade_chain_is_not_calendar_portfolio_return"])

    def test_all_executed_trades_have_prior_regimes_and_reconcile(self):
        meta = [
            {"trade_date": "2025-05-05", "market_state": "BULL",
             "market_volatility_state": "HIGH", "ticker_volume_state": "RVOL_GE_2"},
            {"trade_date": "2025-05-06", "market_state": "BEAR",
             "market_volatility_state": "LOW", "ticker_volume_state": "RVOL_LT_2"},
            {"trade_date": "2025-05-07", "market_state": "TRANSITION",
             "market_volatility_state": "LOW", "ticker_volume_state": "RVOL_LT_2"},
        ]
        trades = [
            {"entry_date": "2025-05-05", "net_return": .01,
             "trading_sessions_held": 1, "exit_reason": "TIME_CLOSE"},
            {"entry_date": "2025-05-07", "net_return": -.01,
             "trading_sessions_held": 2, "exit_reason": "STOP"}
        ]
        rr = ex_ante_reward_risk()
        r = audited_cohort(trades, [], meta, rr["planned_stop_loss_net_fraction"])
        self.assertEqual(r["total_executed"], 2)
        market = r["by_axis"]["market_state"]
        self.assertEqual(market["BULL"]["count"], 1)
        self.assertEqual(market["BEAR"]["count"], 0)
        self.assertEqual(market["TRANSITION"]["count"], 1)
        self.assertEqual(sum(v["count"] for v in market.values()), 2)
        with self.assertRaises(ValueError):
            audited_cohort([{"entry_date": "2025-05-08", "net_return": .01}],
                           [], meta, rr["planned_stop_loss_net_fraction"])


if __name__ == "__main__":
    unittest.main()
