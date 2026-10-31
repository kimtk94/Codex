"""Offline contracts for 100-fold training stability diagnostics."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.kalman_integrated_regime.study_100 import (
    draw_training_blocks, quantiles, compare_daily, evaluate_year
)
from research.kalman_integrated_regime import run as base


class Study100Contracts(unittest.TestCase):
    def test_block_draw_deterministic_and_training_only(self):
        a = draw_training_blocks(125, 10, np.random.default_rng(123))
        b = draw_training_blocks(125, 10, np.random.default_rng(123))
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(len(a), 125)
        self.assertTrue(((a >= 0) & (a < 125)).all())
        self.assertTrue(np.any(np.diff(a) == 1))
        self.assertLess(len(set(a)), 125)

    def test_quantiles_on_known_values(self):
        values = quantiles(list(range(100)))
        self.assertAlmostEqual(values["median"], 49.5)
        self.assertLessEqual(values["p05"], values["median"])
        self.assertLessEqual(values["median"], values["p95"])

    def test_price_audit_flags_adjustment_deviations(self):
        with tempfile.TemporaryDirectory() as t:
            day = pd.date_range("2024-01-02", periods=120, freq="B")
            sip = pd.DataFrame({"date_ny": day, "close_qld": [100.] * 120,
                                "close_qqq": [200.] * 120})
            old = sip.copy()
            old["close_qld"] *= 0.95
            s, o = Path(t) / "sip.csv", Path(t) / "legacy.csv"
            sip.to_csv(s, index=False)
            old.to_csv(o, index=False)
            result = compare_daily(s, o)
            self.assertEqual(result["status"], "CHECK_ADJUSTMENT_OR_VENDOR")
            self.assertEqual(result["comparison"]["QLD"]["sessions_above_0p5pct"], 120)
            self.assertEqual(result["comparison"]["QQQ"]["sessions_above_0p5pct"], 0)

    def test_retraining_year_purges_future_test_labels(self):
        train_days = pd.date_range("2024-01-02", periods=120, freq="B")
        test_days = pd.date_range("2025-01-02", periods=35, freq="B")
        days = train_days.append(test_days)
        rng = np.random.default_rng(119)
        feat = pd.DataFrame(rng.normal(size=(len(days), len(base.PRICE + base.EXTRA))),
                            columns=base.PRICE + base.EXTRA, index=days)
        feat["vix_lag1"] = 20 + np.arange(len(days)) * 0.05
        events = pd.DataFrame({"date": days, "entry_date": days,
                               "exit_date": days + pd.Timedelta(days=1),
                               "positive": [int(i % 3 == 0) for i in range(len(days))],
                               "net_return": [0.04 if i % 3 == 0 else -0.03 for i in range(len(days))]})
        complete = {dt: pd.DataFrame({"close": [100.]}) for dt in test_days}
        # Only 3 fits for fast offline contract tests; production CLI requires 100.
        v = evaluate_year(feat, events, complete, 2025, repeats=3, block_size=10, seed=11)
        self.assertEqual(v["retraining_repeats"], 3)
        self.assertEqual(v["train_samples"], 120)
        self.assertEqual(v["fixed_test_samples"], 35)
        self.assertEqual(len(v["models"]), 2)
        self.assertLess(v["train_last_exit"], "2025-01-01")
        again = evaluate_year(feat, events, complete, 2025, repeats=3, block_size=10, seed=11)
        self.assertEqual(v, again)


if __name__ == "__main__":
    unittest.main()
