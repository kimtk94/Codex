"""Read-only P0 provenance attribution contract; no remote calls or secrets."""
from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from provenance_audit import (compare_numeric_frames, fingerprint_feature_row,
                              training_digest, model_digest)
from train import COLUMNS, model


class LineageContracts(unittest.TestCase):
    def test_numeric_price_values_vs_serialization_difference(self):
        d = pd.bdate_range("2026-11-02", periods=10)
        left = pd.DataFrame({
            "open": np.linspace(100, 110, 10),
            "high": np.linspace(101, 111, 10),
            "low": np.linspace(99, 109, 10),
            "close": np.linspace(100.5, 110.5, 10),
            "volume": np.arange(10) + 1,
        }, index=d)
        # Serialization/metadata differences alone must not count as price drift.
        identical, dates, same = compare_numeric_frames(
            left, left.copy(), "SPY", "raw_OHLCV", expected_date=str(d[-1].date()))
        self.assertTrue(same)
        self.assertEqual(dates, [])
        self.assertTrue(all(x["changed_sessions"] == 0 for x in identical))
        modified = left.copy()
        modified.at[d[3], "close"] *= 1.02
        differences, sessions, same = compare_numeric_frames(
            left, modified, "SPY", "raw_OHLCV", expected_date=str(d[-1].date()))
        self.assertFalse(same)
        self.assertEqual(sessions[0]["date"], str(d[3].date()))
        self.assertEqual(sessions[0]["changed_columns"], "close")
        self.assertEqual(next(x["changed_sessions"] for x in differences
                              if x["column"] == "close"), 1)

    def test_global_adjusted_price_scale_distinct_from_individual_bar_error(self):
        d = pd.bdate_range("2024-01-02", periods=30)
        a = pd.DataFrame({"close": np.linspace(100., 150., 30)}, index=d)
        global_scale = a * 1.015
        col, _, same = compare_numeric_frames(
            a, global_scale, "SPY", "raw_OHLCV", expected_date=str(d[-1].date()))
        self.assertFalse(same)
        self.assertTrue(col[0]["global_multiplicative_rescale"])
        self.assertAlmostEqual(col[0]["median_right_over_left_ratio"], 1.015)
        broken = global_scale.copy()
        broken.iloc[8, 0] *= 1.1
        col2, _, _ = compare_numeric_frames(
            a, broken, "SPY", "raw_OHLCV", expected_date=str(d[-1].date()))
        self.assertGreater(col2[0]["p95_abs_residual_from_median_scale"], 1e-4)

    def test_price_revision_inside_tolerance_ignored(self):
        d = pd.bdate_range("2026-11-02", periods=6)
        left = pd.DataFrame({"close": np.arange(100., 106.)}, index=d)
        right = left.copy()
        right.iloc[0, 0] += 1e-11
        columns, dates, same = compare_numeric_frames(
            left, right, "SPY", "raw_OHLCV", expected_date=str(d[-1].date()))
        self.assertTrue(same)
        self.assertFalse(dates)

    def test_removed_timestamp_is_not_silent(self):
        dates = pd.bdate_range("2026-11-02", periods=6)
        original = pd.DataFrame({"close": np.arange(6.) + 100}, index=dates)
        altered = original.drop(index=dates[2])
        result, dates_out, same = compare_numeric_frames(
            original, altered, "SPY", "raw_OHLCV", expected_date=str(dates[-1].date()))
        self.assertFalse(same)
        self.assertEqual(result[0]["missing_from_right"], 1)

    def test_training_vs_asof_change_separately_identified(self):
        d = pd.bdate_range("2023-01-02", periods=520)
        x = pd.DataFrame(index=d)
        for i, col in enumerate(COLUMNS):
            x[col] = i + np.sin(np.arange(len(d)) / 12)
        x["exit_date"] = pd.Series(d, index=d).shift(-4)
        x["net_return"] = np.where(np.arange(len(d)) % 3 == 0, .03, -.01)
        h1, rows1 = training_digest(x, 2024)
        asof = str(d[-1].date())
        s1 = fingerprint_feature_row(x, asof)
        latest_changed = x.copy()
        latest_changed.loc[latest_changed.index[-1], COLUMNS[0]] += 1.0
        h2, rows2 = training_digest(latest_changed, 2024)
        s2 = fingerprint_feature_row(latest_changed, asof)
        self.assertEqual(h1, h2)
        self.assertEqual(rows1, rows2)
        self.assertNotEqual(s1, s2)
        past_changed = x.copy()
        past_changed.loc[past_changed.index[10], COLUMNS[1]] += 1.0
        h3, rows3 = training_digest(past_changed, 2024)
        self.assertNotEqual(h1, h3)
        self.assertEqual(rows1, rows3)
        self.assertEqual(s1, fingerprint_feature_row(past_changed, asof))

    def test_coefficients_hash_repeatable_on_identical_input(self):
        x = np.arange(320 * len(COLUMNS), dtype=float).reshape(320, len(COLUMNS))
        y = np.arange(320) % 2
        a, b = model(), model()
        a.fit(x, y)
        b.fit(x, y)
        self.assertEqual(model_digest(a), model_digest(b))


if __name__ == "__main__":
    unittest.main()
