from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_v3.kr_candidate import (
    candidate_id,
    expanding_walk_forward_oof,
    safe_pre_forward,
    select_candidate_and_policy,
    update_forward_ledgers,
)


class ModelV3KRCandidateTests(unittest.TestCase):
    def make_matrix(self, n: int = 560) -> pd.DataFrame:
        rng = np.random.default_rng(20260922)
        dates = pd.bdate_range("2024-07-01", periods=n)
        f1 = rng.normal(size=n)
        f2 = rng.normal(size=n)
        f3 = rng.normal(size=n)
        noise = rng.normal(scale=0.55, size=n)
        latent = 1.2 * f1 - 0.5 * f2 + 0.25 * f3 + noise
        label = (latent > 0.0).astype(float)
        forward_return = np.where(label > 0, 0.018, -0.012)
        forward_return = forward_return + rng.normal(0.0, 0.004, size=n)

        data = {
            "as_of": dates,
            "anchor_close": 100.0 * np.cumprod(
                1.0 + rng.normal(0.0003, 0.007, size=n)
            ),
            "target_forward_return": forward_return,
            "target_label": label,
        }
        for i in range(1, 25):
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
            "version": "kalman_model_v3_003_kr_test",
            "dataset_version": "matrix_test",
            "feature_set": "market_tools_v2_002",
            "forward_start": forward_start.isoformat(),
            "minimum_feature_coverage": 0.8,
            "candidate_feature_counts": [8, 16],
            "candidate_c": [0.001, 0.01],
            "candidate_class_weight": [None],
            "walk_forward": {
                "initial_train_observations": 180,
                "test_block_observations": 21,
                "horizon_purge_observations": 5,
                "minimum_oof_rows": 126,
            },
            "markets": {
                "KR": {
                    "symbol": "KOSPI",
                    "strategy_version": "TEST",
                    "horizon_observations": 5,
                }
            },
        }

    def evaluation_spec(self, forward_start: pd.Timestamp) -> dict:
        return {
            "forward_start": forward_start.isoformat(),
            "rolling_score_policy": {
                "lookback_observations": 60,
                "minimum_history_observations": 30,
            },
            "policy_selection": {
                "minimum_nonoverlap_entries": 8,
            },
            "costs": {"round_trip_cost_bps": 10.0},
            "promotion_gate": {
                "minimum_forward_observations_for_interpretation": 60,
                "minimum_forward_observations_for_promotion": 120,
                "minimum_nonoverlap_entries_for_promotion": 8,
                "minimum_incremental_alpha_mean_net": 0.0,
                "minimum_win_rate_lift": 0.0,
                "minimum_net_compounded_return": 0.0,
            },
            "markets": {
                "KR": {
                    "horizon_observations": 5,
                    "candidate_top_fractions": [0.2, 0.3, 0.4],
                }
            },
        }

    def test_forward_boundary_purges_last_horizon_rows(self) -> None:
        matrix = self.make_matrix(420)
        forward_start = pd.Timestamp(matrix.iloc[-20]["as_of"])
        safe, audit = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=5,
        )
        pre = matrix.loc[matrix["as_of"] < forward_start]
        expected_last = pd.Timestamp(pre.iloc[-6]["as_of"])
        self.assertEqual(pd.Timestamp(safe["as_of"].max()), expected_last)
        self.assertEqual(audit["purged_boundary_rows"], 5)
        self.assertFalse(audit["target_outcome_crosses_forward_boundary"])

    def test_expanding_oof_has_horizon_purge(self) -> None:
        matrix = self.make_matrix(520)
        forward_start = pd.Timestamp(matrix.iloc[-10]["as_of"])
        spec = self.model_spec(forward_start)
        safe, _ = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=5,
        )
        oof, audit = expanding_walk_forward_oof(
            safe,
            spec=spec,
            horizon=5,
        )
        self.assertGreaterEqual(audit["fold_count"], 2)
        for fold in audit["folds"]:
            train_end = pd.Timestamp(fold["train_end"])
            test_start = pd.Timestamp(fold["test_start"])
            self.assertLess(train_end, test_start)
            self.assertEqual(fold["purge_observations"], 5)
        for candidate in oof.values():
            self.assertGreaterEqual(len(candidate), 126)

    def test_oof_selects_locked_pre_forward_policy(self) -> None:
        matrix = self.make_matrix(560)
        forward_start = pd.Timestamp(matrix.iloc[-8]["as_of"])
        model_spec = self.model_spec(forward_start)
        evaluation_spec = self.evaluation_spec(forward_start)
        safe, _ = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=5,
        )
        oof, _ = expanding_walk_forward_oof(
            safe,
            spec=model_spec,
            horizon=5,
        )
        hp, policy, audit = select_candidate_and_policy(
            oof,
            model_spec=model_spec,
            evaluation_spec=evaluation_spec,
            horizon=5,
        )
        self.assertIn(hp["feature_count"], {8, 16})
        self.assertIn(policy.top_fraction, {0.2, 0.3, 0.4})
        self.assertLess(pd.Timestamp(policy.selection_end), forward_start)
        self.assertEqual(
            policy.source,
            "EXPANDING_WALK_FORWARD_OOF_PRE_FORWARD_ONLY",
        )
        self.assertEqual(audit["forward_rows_used_for_selection"], 0)
        self.assertTrue(audit["pre_forward_gate_pass"])
        self.assertGreater(
            audit["selected_oof_strategy_metrics"][
                "nonoverlap_incremental_alpha_mean_net"
            ],
            0.0,
        )

    def test_forward_ledgers_are_append_only(self) -> None:
        forward_start = pd.Timestamp("2026-09-23")
        artifact = {
            "artifact_schema": "kalman_rank_logit_json_v3",
            "selected_features": ["f1"],
            "imputer_medians": {"f1": 0.0},
            "scaler_mean": {"f1": 0.0},
            "scaler_scale": {"f1": 1.0},
            "coefficients": {"f1": 1.0},
            "intercept": 0.0,
        }
        first = pd.DataFrame(
            {
                "as_of": pd.to_datetime(
                    ["2026-09-23", "2026-09-24", "2026-09-25"]
                ),
                "anchor_close": [100.0, 101.0, 102.0],
                "target_forward_return": [0.02, np.nan, np.nan],
                "target_label": [1.0, np.nan, np.nan],
                "f1": [0.2, 0.4, 0.6],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            score_path = root / "scores.parquet"
            outcome_path = root / "outcomes.parquet"

            eval1, audit1 = update_forward_ledgers(
                first,
                artifact,
                forward_start=forward_start,
                score_ledger_path=score_path,
                outcome_ledger_path=outcome_path,
            )
            frozen_scores = dict(zip(eval1["as_of"], eval1["score"]))
            self.assertEqual(audit1["score_rows"], 3)
            self.assertEqual(audit1["outcome_rows"], 1)

            revised = first.copy()
            revised.loc[:, "f1"] = [9.0, 9.0, 9.0]
            revised.loc[0, "target_forward_return"] = -0.50
            revised.loc[0, "target_label"] = 0.0
            revised.loc[1, "target_forward_return"] = 0.03
            revised.loc[1, "target_label"] = 1.0
            revised = pd.concat(
                [
                    revised,
                    pd.DataFrame(
                        {
                            "as_of": [pd.Timestamp("2026-09-28")],
                            "anchor_close": [103.0],
                            "target_forward_return": [np.nan],
                            "target_label": [np.nan],
                            "f1": [0.8],
                        }
                    ),
                ],
                ignore_index=True,
            )

            eval2, audit2 = update_forward_ledgers(
                revised,
                artifact,
                forward_start=forward_start,
                score_ledger_path=score_path,
                outcome_ledger_path=outcome_path,
            )
            for as_of, score in frozen_scores.items():
                got = float(
                    eval2.loc[eval2["as_of"] == as_of, "score"].iloc[0]
                )
                self.assertAlmostEqual(got, float(score))

            first_outcome = float(
                eval2.loc[
                    eval2["as_of"] == pd.Timestamp("2026-09-23"),
                    "target_forward_return",
                ].iloc[0]
            )
            self.assertAlmostEqual(first_outcome, 0.02)
            second_outcome = float(
                eval2.loc[
                    eval2["as_of"] == pd.Timestamp("2026-09-24"),
                    "target_forward_return",
                ].iloc[0]
            )
            self.assertAlmostEqual(second_outcome, 0.03)
            self.assertEqual(audit2["new_score_rows"], 1)
            self.assertEqual(audit2["new_outcome_rows"], 1)

    def test_candidate_id_is_deterministic(self) -> None:
        item = {
            "feature_count": 16,
            "C": 0.001,
            "class_weight": None,
        }
        self.assertEqual(candidate_id(item), "f16_c0.001_cwnone")


if __name__ == "__main__":
    unittest.main()
