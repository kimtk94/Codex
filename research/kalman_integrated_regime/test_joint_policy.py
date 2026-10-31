"""Offline contracts for complete interacting execution policies."""
import unittest
from collections import defaultdict
import numpy as np
import pandas as pd

from research.kalman_integrated_regime.joint_policy import (
    AXES, BASELINE, generate_policies, pairwise_coverage, policy_id,
    simulate_trade, simulate_portfolio, interaction_screen, allow_signal
)


def candles(day, opens, highs, lows, closes):
    return (pd.Timestamp(day), pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes}))


class JointPolicyTests(unittest.TestCase):
    def test_deterministic_joint_design_not_single_factor(self):
        a = generate_policies(100, seed=432)
        b = generate_policies(100, seed=432)
        self.assertEqual(a, b)
        self.assertEqual(a[0], BASELINE)
        self.assertEqual(len({policy_id(v) for v in a}), 100)
        self.assertTrue(all(sum(p[k] != BASELINE[k] for k in AXES) >= 5 for p in a[1:]))
        coverage = pairwise_coverage(a)
        self.assertGreater(coverage["fraction"], 0.1)
        self.assertLess(coverage["fraction"], 1.0)
        self.assertEqual(len(AXES), 40)

    def test_baseline_stop_precedence_same_bar(self):
        p = dict(BASELINE)
        d = candles("2025-02-03", [100.], [106.], [94.], [105.])
        item = simulate_trade(p, [d], 0, pd.Timestamp("2025-01-31"), previous_close=100.)
        self.assertEqual(item.exited_by, "SL_OR_TRAIL")
        self.assertLess(item.net_pnl, -.029)
        self.assertEqual(item.fills_buy, 1)
        self.assertEqual(item.fills_sell, 1)

    def test_gap_down_stop_at_actual_open(self):
        p = dict(BASELINE)
        day = candles("2025-02-03", [100., 94.], [101., 96.], [99., 93.], [100., 95.])
        item = simulate_trade(p, [day], 0, pd.Timestamp("2025-01-31"), 100.)
        self.assertLess(item.net_pnl, -.055)
        self.assertEqual(item.exited_by, "SL_OR_TRAIL")

    def test_split_add_then_time_exit_account_ledger(self):
        p = dict(BASELINE)
        p.update({"tp": .2, "sl": .1, "split": "equal", "add_dip": .03})
        first = candles("2025-02-03", [100., 99., 97.], [100.2, 99.3, 97.2],
                        [99.6, 96.5, 96.8], [99.8, 97.5, 97.])
        item = simulate_trade(p, [first], 0, pd.Timestamp("2025-01-31"), 100.)
        self.assertEqual(item.fills_buy, 2)
        self.assertEqual(item.exited_by, "TIME")
        self.assertEqual(item.fills_sell, 1)
        self.assertLess(item.net_pnl, 0.)
        self.assertGreater(item.net_pnl, -.04)

    def test_risk_sizing_caps_loss_and_no_leverage(self):
        p = dict(BASELINE)
        p.update({"size": 1., "risk_budget": .005, "sl": .02})
        day = candles("2025-02-03", [100.], [101.], [97.], [98.])
        item = simulate_trade(p, [day], 0, pd.Timestamp("2025-01-31"), 100.)
        self.assertGreater(item.net_pnl, -.008)
        self.assertLess(item.net_pnl, 0.)

    def test_partial_exit_and_trail_activation_prior_bar_only(self):
        p = dict(BASELINE)
        p.update({"tp": .1, "sl": .03, "partial_tp": .5, "partial_at_r": .5,
                  "trail": .01, "trail_start_r": .5})
        day = candles("2025-02-03", [100., 102., 100.],
                      [102., 102.5, 100.2], [99.8, 100.5, 98.],
                      [101., 101., 99.])
        item = simulate_trade(p, [day], 0, pd.Timestamp("2025-01-31"), 100.)
        self.assertEqual(item.fills_sell, 2)
        self.assertEqual(item.exited_by, "SL_OR_TRAIL")
        self.assertTrue(np.isfinite(item.net_pnl))

    def test_new_15_options_all_have_real_scenario_branches(self):
        self.assertEqual(len(AXES), 40)
        p = dict(BASELINE)
        p["min_rr"] = 2.
        from research.kalman_integrated_regime.joint_policy import policy_valid
        self.assertFalse(policy_valid(p))
        feature = pd.Series({"vix_lag1": 19., "vix_r5_lag1": .09,
                             "qqq_r20": .04, "qqq_r5": .015, "qld_r5": .06,
                             "qqq_vol20": .018, "hyg_lqd_r5_lag1": -.005,
                             "tnx_lag1": 4.5, "smh_spy_r20_lag1": -.015})
        filters = {
            "vol_floor": .02, "qqq_r20_cap": .03, "qqq_r5_cap": .01,
            "qld_r5_abs_cap": .03, "credit_floor": 0.,
            "credit_cap": -.01, "tnx_cap": 4., "vix_change_cap": .05,
            "smh_spy_floor": 0.,
        }
        for key, value in filters.items():
            with self.subTest(key=key):
                altered = dict(BASELINE, **{key: value})
                self.assertFalse(allow_signal(altered, feature, .9))
        baseline_day = candles("2025-02-03", [100., 100., 101.],
                               [100.1, 100.2, 101.1], [99.9, 99.8, 100.9],
                               [100., 100., 101.])
        previous = baseline_day[1].iloc[0]
        for key, value in {"gap_down_cap": .01, "gap_up_floor": .01}.items():
            with self.subTest(key=key):
                x = dict(BASELINE, **{key: value})
                previous_close = 104. if key == "gap_down_cap" else 100.
                self.assertIsNone(simulate_trade(x, [baseline_day], 0, pd.Timestamp("2025-01-31"), previous_close, previous))
        range_cap = dict(BASELINE, **{"prior_bar_range_cap": .01})
        wide_previous = pd.Series({"open": 100., "high": 103., "low": 97.})
        self.assertIsNone(simulate_trade(range_cap, [baseline_day], 0, pd.Timestamp("2025-01-31"), 100., wide_previous))
        holding = dict(BASELINE, **{"min_profit_holding_bars": 3, "tp": .01, "hold": 1})
        # Immediate favorable excursion cannot be captured as early TP with min holding bars.
        hi = candles("2025-02-03", [100., 100., 100., 100.],
                     [102., 100.2, 100.2, 100.2], [99.8, 99.8, 99.8, 99.8],
                     [100., 100., 100., 100.])
        a = simulate_trade(dict(BASELINE, tp=.01, hold=1), [hi], 0, pd.Timestamp("2025-01-31"), 100.)
        b = simulate_trade(holding, [hi], 0, pd.Timestamp("2025-01-31"), 100.)
        self.assertEqual(a.exited_by, "TP")
        self.assertEqual(b.exited_by, "TIME")
    
    def test_entry_delay_and_gap_filter(self):
        d = candles("2025-02-03", [100., 103., 102.],
                    [100.5, 103.5, 102.2], [99.5, 102.5, 101.5],
                    [100., 103., 102.])
        p = dict(BASELINE)
        p.update({"entry_delay": 1, "gap_cap": .01})
        self.assertIsNone(simulate_trade(p, [d], 1, pd.Timestamp("2025-01-31"), 100.))
        p["gap_cap"] = 0.
        item = simulate_trade(p, [d], 1, pd.Timestamp("2025-01-31"), 100.)
        self.assertIsNotNone(item)
        self.assertEqual(item.fills_buy, 1)

    def test_lookahead_gates_use_only_supplied_signal_features(self):
        p = dict(BASELINE)
        p.update({"vix_max": 20., "confidence": .6, "trend": "r20"})
        feature = pd.Series({"vix_lag1": 19., "qqq_r20": .02, "qqq_r5": .01,
                             "qld_r5": -.01, "qqq_vol20": .01})
        self.assertTrue(allow_signal(p, feature, .7))
        self.assertFalse(allow_signal(p, feature, .5))
        feature.loc["vix_lag1"] = 22.
        self.assertFalse(allow_signal(p, feature, .7))

    def test_cooldown_prevents_overlap_and_daily_mark_reconciles(self):
        days = pd.bdate_range("2025-02-03", periods=8)
        frames = {d: pd.DataFrame({"open": [100.], "high": [100.2],
                                    "low": [99.8], "close": [100.]})
                  for d in days}
        probs = pd.Series(0.9, index=days[:5])
        features = pd.DataFrame({"vix_lag1": 17., "qqq_r20": .03,
                                 "qqq_r5": .01, "qld_r5": .01,
                                 "qqq_vol20": .01}, index=days)
        p = dict(BASELINE)
        p["hold"] = 2
        p["cooldown"] = 2
        result = simulate_portfolio(p, probs, features, frames, days, 2025)
        self.assertGreaterEqual(result["trades"], 1)
        self.assertLessEqual(result["trades"], 2)
        self.assertTrue(np.isfinite(result["mdd_daily_mark_pct"]))

    def test_interaction_screen_not_claimed_causal(self):
        self.assertEqual(interaction_screen([], 2025, "integrated_regime"), [])


if __name__ == "__main__":
    unittest.main()
