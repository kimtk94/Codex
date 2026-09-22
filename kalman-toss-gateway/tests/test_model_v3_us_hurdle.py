from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.model_v3.us_hurdle_candidate import (
    evaluate_half_stability,
    select_us_candidate,
    with_hurdle_label,
)


class ModelV3USHurdleTests(unittest.TestCase):
    def make_matrix(self, n: int = 620) -> pd.DataFrame:
        rng = np.random.default_rng(230923)
        dates = pd.bdate_range("2024-01-02", periods=n)
        f1 = rng.normal(size=n)
        f2 = rng.normal(size=n)
        f3 = rng.normal(size=n)
        edge = 0.007 * f1 - 0.002 * f2 + rng.normal(0.0, 0.006, size=n)
        ret = edge + 0.0015
        label = (ret > 0.0).astype(float)

        data = {
            "as_of": dates,
            "anchor_close": 100.0 * np.cumprod(
                1.0 + rng.normal(0.0004, 0.008, size=n)
            ),
            "target_forward_return": ret,
            "target_label": label,
        }
        for i in range(1, 20):
            if i == 1:
                data[f"f{i}"] = f1
            elif i == 2:
                data[f"f{i}"] = f2
            elif i == 3:
                data[f"f{i}"] = f3
            else:
                data[f"f{i}"] = rng.normal(size=n)
        return pd.DataFrame(data)

    def model_spec(self, forward_start: pd.Timestamp) -> dict:
        return {
            "version": "kalman_model_v3_003_us_hurdle_test",
            "dataset_version": "test",
            "feature_set": "test",
            "forward_start": forward_start.isoformat(),
            "objective": "RANK_ALPHA_AFTER_TARGET_REDESIGN",
            "target_design": "ABSOLUTE_5D_FORWARD_RETURN_HURDLE",
            "target_hurdles": [0.0025, 0.005, 0.01],
            "minimum_feature_coverage": 0.8,
            "candidate_feature_counts": [8, 16],
            "candidate_c": [0.001, 0.01],
            "candidate_class_weight": [None, "balanced"],
            "walk_forward": {
                "initial_train_observations": 180,
                "test_block_observations": 21,
                "horizon_purge_observations": 5,
                "minimum_oof_rows": 126,
            },
            "selection_gate": {
                "minimum_nonoverlap_entries": 12,
                "minimum_half_nonoverlap_entries": 4,
            },
            "markets": {
                "US": {
                    "symbol": "SPY",
                    "strategy_version": "TEST_US_HURDLE",
                    "horizon_observations": 5,
                }
            },
        }

    def eval_spec(self, forward_start: pd.Timestamp) -> dict:
        return {
            "forward_start": forward_start.isoformat(),
            "rolling_score_policy": {
                "lookback_observations": 60,
                "minimum_history_observations": 30,
            },
            "policy_selection": {"minimum_nonoverlap_entries": 8},
            "costs": {"round_trip_cost_bps": 10.0},
            "promotion_gate": {},
            "markets": {
                "US": {
                    "horizon_observations": 5,
                    "candidate_top_fractions": [0.2, 0.3, 0.4],
                }
            },
        }

    def test_hurdle_label_changes_target(self) -> None:
        frame = pd.DataFrame(
            {
                "target_forward_return": [-0.01, 0.003, 0.006, np.nan],
                "target_label": [0.0, 1.0, 1.0, np.nan],
            }
        )
        out = with_hurdle_label(frame, 0.005)
        self.assertEqual(out["target_label"].iloc[0], 0.0)
        self.assertEqual(out["target_label"].iloc[1], 0.0)
        self.assertEqual(out["target_label"].iloc[2], 1.0)
        self.assertTrue(pd.isna(out["target_label"].iloc[3]))

    def test_stable_hurdle_candidate_can_pass(self) -> None:
        matrix = self.make_matrix()
        forward_start = pd.Timestamp(matrix.iloc[-8]["as_of"])
        model_spec = self.model_spec(forward_start)
        eval_spec = self.eval_spec(forward_start)

        safe = matrix.loc[matrix["as_of"] < forward_start].copy().iloc[:-5]
        hp, policy, audit, selected_oof, target = select_us_candidate(
            safe,
            model_spec=model_spec,
            evaluation_spec=eval_spec,
            horizon=5,
        )

        self.assertIsNotNone(hp)
        self.assertIsNotNone(policy)
        self.assertIsNotNone(selected_oof)
        self.assertIsNotNone(target)
        self.assertGreater(audit["joint_gate_passing_count"], 0)
        self.assertTrue(audit["pre_forward_gate_pass"])
        self.assertIn(target["target_hurdle"], {0.0025, 0.005, 0.01})
        self.assertIn(policy.top_fraction, {0.2, 0.3, 0.4})
        self.assertEqual(audit["forward_rows_used_for_selection"], 0)

        halves = audit["selected_stability_halves"]
        self.assertGreater(
            halves["first_half"]["nonoverlap_incremental_alpha_mean_net"],
            0.0,
        )
        self.assertGreater(
            halves["second_half"]["nonoverlap_incremental_alpha_mean_net"],
            0.0,
        )

    def test_half_stability_reports_both_periods(self) -> None:
        frame = self.make_matrix(300)
        frame["score"] = np.linspace(0.0, 1.0, len(frame))
        result = evaluate_half_stability(
            frame,
            top_fraction=0.3,
            evaluation_spec=self.eval_spec(pd.Timestamp("2026-09-23")),
            horizon=5,
        )
        self.assertIn("first_half", result)
        self.assertIn("second_half", result)
        self.assertGreater(
            result["first_half"]["policy_ready_rows"],
            0,
        )
        self.assertGreater(
            result["second_half"]["policy_ready_rows"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
