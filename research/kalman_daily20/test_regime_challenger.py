"""Offline bear-regime challenger guardrails; fixed thresholds and OOS isolation."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from daily20 import load_spec
from portfolio import market_state
from regime_challenger import (
    BEAR_VIX_MAX, COSTS, ML_THRESHOLD, SCENARIOS,
    bear_gate, compute_scenarios, fit_bear_year, regime_days, rule_gate
)
from train import COLUMNS, HOLD


def oos_frame():
    dates = pd.bdate_range("2022-01-03", periods=750)
    frame = pd.DataFrame(index=dates)
    for idx, field in enumerate(COLUMNS):
        frame[field] = np.sin(np.arange(len(dates)) / (10 + idx)) + idx / 30.
    frame["spy_above200_lag"] = 0.0
    frame["vix_lag"] = 18.0
    frame["net_return"] = np.where(np.arange(len(frame)) % 3 == 0, .02, -.01)
    frame["exit_date"] = pd.Series(dates, index=dates).shift(-HOLD)
    return frame


class BearOOSContracts(unittest.TestCase):
    def test_bear_regime_uses_prior_session_and_vix_gate(self):
        dates = pd.bdate_range("2024-01-02", periods=4)
        f = pd.DataFrame({
            "spy_above200_lag": [0.0, 1.0, 0.0, 0.0],
            "vix_lag": [18.0, 18.0, 46.0, 35.0],
            "rsi14": [35., 40., 50., 45.],
            "ret1": [0.01] * 4,
            "macd_hist": [0.0, 1.0, 2.0, 3.0],
        }, index=dates)
        self.assertEqual(bear_gate(f).tolist(), [True, False, False, True])
        self.assertEqual(rule_gate(f).tolist(), [False, False, False, True])
        self.assertEqual(BEAR_VIX_MAX, 45.0)
        self.assertEqual(ML_THRESHOLD, .60)

    def test_bear_model_never_learns_test_year_future_labels(self):
        f = oos_frame()
        m1, test1, info1 = fit_bear_year(f, 2024)
        self.assertEqual(info1["status"], "OOS_BEAR_MODEL_EVALUATED")
        self.assertGreaterEqual(info1["bear_training_rows"], 126)
        self.assertTrue((f.loc[f.index.year >= 2024].index >= pd.Timestamp("2024-01-01")).all())
        pred1 = m1.predict_proba(test1[COLUMNS])[:, 1]
        revised = f.copy()
        revised.loc[revised.index.year == 2024, "net_return"] *= -1
        m2, test2, info2 = fit_bear_year(revised, 2024)
        pred2 = m2.predict_proba(test2[COLUMNS])[:, 1]
        np.testing.assert_allclose(pred1, pred2, rtol=0, atol=1e-12)
        self.assertEqual(info1["bear_training_rows"], info2["bear_training_rows"])

    def test_training_label_purge_across_year_boundary(self):
        f = oos_frame()
        # Ensure all last-2023 rows with exits in 2024 must be dropped from train.
        train_f, _, info = fit_bear_year(f, 2024)
        self.assertIsNotNone(train_f)
        pre_boundary = f[(f.index < "2024-01-01") & (f["exit_date"] < "2024-01-01")]
        self.assertEqual(info["bear_training_rows"], int(bear_gate(pre_boundary).sum()))
        spillover = f[(f.index < "2024-01-01") & (f["exit_date"] >= "2024-01-01")]
        self.assertTrue(len(spillover) >= 1)

    def test_insufficient_bear_history_is_explicit(self):
        f = oos_frame()
        f.loc[f.index.year < 2024, "spy_above200_lag"] = 1.0
        fitted, test, info = fit_bear_year(f, 2024)
        self.assertIsNone(fitted)
        self.assertEqual(info["status"], "INSUFFICIENT_BEAR_TRAINING")
        self.assertEqual(info["bear_training_rows"], 0)

    def test_scenarios_do_not_promote_challenger_and_use_same_cash(self):
        days = pd.bdate_range("2023-01-02", periods=700)
        spy = np.r_[np.linspace(100, 200, 400), np.linspace(200, 120, 300)]
        prices = {
            s: pd.DataFrame({
                "open": (np.full(len(days), 18.) if s == "^VIX" else
                         spy if s == "SPY" else spy * 1.1 if s == "QQQ"
                         else np.full(len(days), 120.)),
                "close": (np.full(len(days), 18.) if s == "^VIX" else
                          spy if s == "SPY" else spy * 1.1 if s == "QQQ"
                          else np.full(len(days), 120.)),
            }, index=days)
            for s in ("SPY", "QQQ", "^VIX", "NVDA")
        }
        state = market_state(prices)
        bull_idx = next(i for i in range(300, 450)
                        if str(days[i].year) == "2024" and bool(state.bull.iloc[i]))
        bear_idx = next(i for i in range(490, 680)
                        if not bool(state.bull.iloc[i]))
        self.assertEqual(regime_days(state, days)["regime_lagged"].iloc[bear_idx], "BEAR")
        def record(i, family, strategy, regime):
            return {
                "symbol": "NVDA", "strategy": strategy,
                "signal_date": str(days[i].date()),
                "entry_date": str(days[i+1].date()),
                "exit_date": str(days[i+4].date()),
                "gross_return": 0., "net_return": -.002,
                "probability": .75 if strategy == "LOGISTIC" else np.nan,
                "regime": regime, "candidate_family": family,
            }
        spec = load_spec()
        with TemporaryDirectory() as root:
            baseline = Path(root) / "base.csv"
            pd.DataFrame([record(bull_idx, "BASE", "LOGISTIC", "BULL")]).to_csv(
                baseline, index=False)
            bear = pd.DataFrame([
                record(bear_idx, "BEAR_LOGISTIC", "LOGISTIC", "BEAR"),
                record(bear_idx, "BEAR_RULE", "TREND_RULE", "BEAR"),
            ])
            m, c, e, annual, reg, _, sessions, _ = compute_scenarios(
                spec, root, baseline, bear, Path(root) / "results", prices=prices)
            self.assertEqual(len(m), len(SCENARIOS) * 2 * len(COSTS))
            self.assertEqual(len(c), len(sessions) * len(m))
            self.assertTrue((c["gross_exposure"] <= 1.0000001).all())
            self.assertTrue((c["cash"] >= -1e-8).all())
            base = m[(m.name == "BULL_BASELINE") & (m.cohort == "ALL_20")
                     & (m.cost_bps == 20)].iloc[0]
            combo = m[(m.name == "BULL_PLUS_BEAR_LOGISTIC") & (m.cohort == "ALL_20")
                      & (m.cost_bps == 20)].iloc[0]
            self.assertEqual(base.executed_trades, 1)
            self.assertEqual(combo.executed_trades, 2)
            self.assertFalse(m["approved_live"].any())


if __name__ == "__main__":
    unittest.main()
