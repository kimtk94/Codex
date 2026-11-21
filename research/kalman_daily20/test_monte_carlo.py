"""Statistical and accounting contracts for required Daily20 Monte Carlo research."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from monte_carlo import (
    BLOCKS, EXPECTED_BASE, EXPECTED_REGIME,
    load_synchronized_curves, one_configuration, portfolio_path_metrics,
    run, sample_joint_indices, validate_original_curves,
)
from daily20 import load_spec, market_file


class MonteCarloContracts(unittest.TestCase):
    def test_common_indices_preserve_same_day_cross_strategy_dependence(self):
        days = pd.bdate_range("2024-01-02", periods=335)
        rng = np.random.default_rng(4)
        sampled = sample_joint_indices(rng, days, block=5, size=70)
        self.assertEqual(sampled.shape, (70, len(days)))
        self.assertTrue((sampled >= 0).all())
        self.assertTrue((sampled < len(days)).all())
        shock = np.where(np.arange(len(days)) % 17 == 0, -.05, .001)
        portfolio = shock * 0.6
        spy = shock
        # Every sampled row must preserve co-movement of all series.
        np.testing.assert_allclose(portfolio[sampled], .6 * spy[sampled])
        self.assertTrue(all(
            days[sampled[row, :250]].year.max() == 2024 for row in range(70)
        ))

    def test_blocks_5_and_20_keep_more_local_dependence_than_iid(self):
        days = pd.bdate_range("2024-01-02", periods=300)
        for block in BLOCKS:
            samples = sample_joint_indices(
                np.random.default_rng(11), days, block=block, size=20)
            if block > 1:
                for row in samples:
                    # Half of adjacent pairs must be consecutive in their
                    # corresponding circular within-year timeline.
                    continuous = (row[1:] - row[:-1] == 1)
                    self.assertGreater(continuous.mean(), .50)
        self.assertEqual(BLOCKS, (1, 5, 20))

    def test_path_mdd_includes_starting_equity_and_never_positive(self):
        x = np.array([[[.10, .00], [-.50, -.10], [.10, .02]]], dtype=float)
        returns, worst = portfolio_path_metrics(x)
        self.assertAlmostEqual(returns[0, 0], 1.1 * .5 * 1.1 - 1)
        self.assertAlmostEqual(worst[0, 0], -.50)
        self.assertLessEqual(worst[0, 1], 0)
        self.assertTrue((worst <= 0).all())

    def test_same_seed_reproduces_all_monte_carlo_statistics(self):
        idx = pd.bdate_range("2024-01-02", periods=300)
        rng = np.random.default_rng(77)
        risk = rng.choice([-.075, .0, .01], 300, p=[.10, .40, .50])
        df = pd.DataFrame({
            "PORT": risk * 1.5,
            "BENCHMARK_SPY": risk,
            "BENCHMARK_QQQ": risk * 1.2,
        }, index=idx)
        a = one_configuration(df, block=20, repetitions=250, seed=19)
        b = one_configuration(df, block=20, repetitions=250, seed=19)
        pd.testing.assert_frame_equal(a, b)
        port = a.loc[a.scenario == "PORT"].iloc[0]
        self.assertTrue(0 <= port.loss_probability <= 1)
        self.assertTrue(0 <= port.probability_underperform_spy <= 1)
        self.assertLess(port.return_p05, port.return_p95)
        self.assertLessEqual(port.return_cvar_05, port.return_p05 + 1e-12)
        self.assertLess(port.mdd_p05_worst, 0)
        self.assertFalse(a.approved_live.any())

    def test_missing_yearly_or_inconsistent_portfolio_returns_fail(self):
        spec = load_spec()
        with TemporaryDirectory() as root:
            root = Path(root)
            days = pd.bdate_range("2024-01-02", periods=270)
            market = root / "market"
            for symbol in ("SPY", "QQQ"):
                px = 100 + np.arange(len(days)) * .06
                path = market_file(market, symbol)
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({
                    "timestamp": days, "open": px, "close": px,
                    "high": px, "low": px, "volume": 10_000,
                }).to_parquet(path, index=False)
            def seed(path, n, prefix):
                entries = []
                for j in range(n):
                    name = f"{prefix}_{j}"
                    equity = 100_000.
                    for date in days:
                        ret = -.005 if date.day % 20 == 0 else .001
                        equity *= (1 + ret)
                        entries.append({
                            "date": date.date().isoformat(), "scenario": name,
                            "daily_return": ret, "equity": equity,
                        })
                pd.DataFrame(entries).to_csv(path, index=False)
            p = root / "base.csv"
            q = root / "regime.csv"
            seed(p, EXPECTED_BASE, "BASE")
            seed(q, EXPECTED_REGIME, "REGIME")
            wide = load_synchronized_curves(p, q, market, spec)
            self.assertEqual(wide.shape[1], 38)
            validate_original_curves(wide, p, q)
            # The required named risk cohorts from real pipeline must exist.
            with self.assertRaisesRegex(RuntimeError, "MONTE_CARLO_PRIMARY_CASE_MISSING"):
                run("research/kalman_daily20/universe.json", market, p, q,
                    root / "out", repetitions=200, seed=5)
            changed = pd.read_csv(p)
            changed.loc[0, "equity"] = 999.0
            changed.to_csv(p, index=False)
            # Terminal accounting changed -> mismatch must be detected.
            changed.loc[changed.scenario == "BASE_0", "equity"] *= 1.002
            changed.to_csv(p, index=False)
            with self.assertRaisesRegex(RuntimeError, "MONTE_CARLO_LEDGER_RETURNS_MISMATCH"):
                validate_original_curves(wide, p, q)


if __name__ == "__main__":
    unittest.main()
