from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.model_v3.evaluation import (
    LockedQuantilePolicy,
    evaluate_forward_gate,
    evaluate_policy,
    non_overlapping_mask,
    rolling_top_quantile_policy,
    select_pre_forward_policy,
)


class ModelV3EvaluationTests(unittest.TestCase):
    def test_rolling_threshold_excludes_current_score(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of": pd.date_range("2026-01-01", periods=8, freq="D"),
                "score": [0.1, 0.2, 0.3, 0.4, 10.0, 0.5, 0.6, 0.7],
                "target_forward_return": [0.0] * 8,
            }
        )
        out = rolling_top_quantile_policy(
            frame,
            top_fraction=0.25,
            lookback_observations=4,
            minimum_history_observations=4,
        )
        # At row 4 the cutoff must use rows 0..3 only, so the current spike
        # cannot inflate its own entry threshold.
        expected = float(np.quantile([0.1, 0.2, 0.3, 0.4], 0.75, method="linear"))
        self.assertAlmostEqual(float(out.loc[4, "score_cutoff"]), expected)
        self.assertTrue(bool(out.loc[4, "selected"]))

    def test_non_overlap_respects_horizon_observations(self) -> None:
        frame = pd.DataFrame(
            {
                "selected": [True, True, True, True, True, True, True, True],
            }
        )
        mask = non_overlapping_mask(frame, horizon_observations=3)
        self.assertEqual(np.flatnonzero(mask).tolist(), [0, 3, 6])

    def test_policy_selection_uses_only_pre_forward_rows(self) -> None:
        n = 180
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        score = np.linspace(0.0, 1.0, n)
        returns = np.where(score > 0.7, 0.03, -0.002)
        frame = pd.DataFrame(
            {
                "as_of": dates,
                "score": score,
                "target_forward_return": returns,
                "anchor_close": 100.0 * np.cumprod(1.0 + np.full(n, 0.001)),
            }
        )
        forward_start = pd.Timestamp("2026-05-01")
        policy, audit = select_pre_forward_policy(
            frame,
            top_fractions=[0.2, 0.3, 0.4],
            forward_start=forward_start,
            lookback_observations=60,
            minimum_history_observations=20,
            horizon_observations=5,
            round_trip_cost_bps=10.0,
            minimum_nonoverlap_entries=3,
        )
        self.assertLess(pd.Timestamp(policy.selection_end), forward_start)
        self.assertFalse(audit["selection_uses_forward_rows"])
        self.assertIn(policy.top_fraction, {0.2, 0.3, 0.4})

    def test_forward_gate_has_no_promotion_before_forward_rows(self) -> None:
        frame = pd.DataFrame(
            {
                "as_of": pd.date_range("2026-01-01", periods=100, freq="D"),
                "score": np.linspace(0.0, 1.0, 100),
                "target_forward_return": np.linspace(-0.01, 0.02, 100),
            }
        )
        policy = LockedQuantilePolicy(
            top_fraction=0.3,
            lookback_observations=60,
            minimum_history_observations=20,
            selection_end="2026-04-09T00:00:00",
        )
        result = evaluate_forward_gate(
            frame,
            policy=policy,
            forward_start="2026-09-23T00:00:00",
            horizon_observations=5,
            round_trip_cost_bps=10.0,
            gate={
                "minimum_forward_observations_for_interpretation": 60,
                "minimum_forward_observations_for_promotion": 120,
                "minimum_nonoverlap_entries_for_promotion": 8,
            },
        )
        self.assertEqual(result["status"], "TRACKING_NO_FORWARD_ROWS")
        self.assertFalse(result["promotion_eligible"])

    def test_forward_gate_can_pass_only_from_forward_evidence(self) -> None:
        rng = np.random.default_rng(7)
        pre_n = 180
        fwd_n = 140
        dates = pd.date_range("2026-01-01", periods=pre_n + fwd_n, freq="D")
        score = rng.normal(size=pre_n + fwd_n)
        returns = rng.normal(0.0, 0.002, size=pre_n + fwd_n)

        # In the forward era only, high score has real positive edge.
        fwd_slice = slice(pre_n, pre_n + fwd_n)
        forward_scores = score[fwd_slice]
        returns[fwd_slice] += np.where(forward_scores > 0.6, 0.025, -0.002)

        frame = pd.DataFrame(
            {
                "as_of": dates,
                "score": score,
                "target_forward_return": returns,
                "anchor_close": 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.005, pre_n + fwd_n)),
            }
        )
        forward_start = dates[pre_n]
        policy = LockedQuantilePolicy(
            top_fraction=0.25,
            lookback_observations=126,
            minimum_history_observations=60,
            selection_end=pd.Timestamp(dates[pre_n - 1]).isoformat(),
        )
        result = evaluate_forward_gate(
            frame,
            policy=policy,
            forward_start=forward_start,
            horizon_observations=5,
            round_trip_cost_bps=10.0,
            gate={
                "minimum_forward_observations_for_interpretation": 60,
                "minimum_forward_observations_for_promotion": 120,
                "minimum_nonoverlap_entries_for_promotion": 8,
                "minimum_incremental_alpha_mean_net": 0.0,
                "minimum_win_rate_lift": 0.0,
                "minimum_net_compounded_return": 0.0,
            },
        )
        self.assertGreaterEqual(result["forward_observations"], 120)
        self.assertGreaterEqual(result["nonoverlap_selected_net"]["rows"], 8)
        self.assertGreater(result["nonoverlap_incremental_alpha_mean_net"], 0.0)
        self.assertGreater(result["nonoverlap_win_rate_lift"], 0.0)
        self.assertTrue(result["promotion_eligible"])
        self.assertTrue(all(result["checks"].values()))

    def test_evaluate_policy_reports_cost_adjusted_alpha(self) -> None:
        n = 200
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        score = np.sin(np.arange(n) / 5.0)
        returns = np.where(score > 0.7, 0.02, -0.001)
        frame = pd.DataFrame(
            {
                "as_of": dates,
                "score": score,
                "target_forward_return": returns,
            }
        )
        result = evaluate_policy(
            frame,
            top_fraction=0.2,
            lookback_observations=60,
            minimum_history_observations=30,
            horizon_observations=5,
            round_trip_cost_bps=10.0,
        )
        self.assertGreater(result["nonoverlap_selected_rows"], 0)
        self.assertIsNotNone(result["nonoverlap_incremental_alpha_mean_net"])
        self.assertIsNotNone(result["nonoverlap_win_rate_lift"])


if __name__ == "__main__":
    unittest.main()
