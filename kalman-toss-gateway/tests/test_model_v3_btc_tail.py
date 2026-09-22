from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.model_v3.btc_tail_candidate import (
    build_reference_with_bridge,
    freeze_btc_model,
    select_tail_candidate,
)
from research.model_v3.kr_candidate import (
    expanding_walk_forward_oof,
    safe_pre_forward,
)


class ModelV3BTCTailTests(unittest.TestCase):
    def make_matrix(self, n: int = 820) -> pd.DataFrame:
        rng = np.random.default_rng(230923)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        f1 = rng.normal(size=n)
        f2 = rng.normal(size=n)
        f3 = rng.normal(size=n)
        latent = 1.5 * f1 + 0.3 * f2 + rng.normal(0, 0.65, size=n)
        label = (latent > 0).astype(float)

        # Tail scores driven by f1 carry especially large positive return.
        tail = f1 > np.quantile(f1, 0.85)
        ret = np.where(label > 0, 0.012, -0.010)
        ret = ret + np.where(tail, 0.055, 0.0)
        ret = ret + rng.normal(0.0, 0.006, size=n)

        data = {
            "as_of": dates,
            "anchor_close": 30000.0 * np.cumprod(
                1.0 + rng.normal(0.0008, 0.018, size=n)
            ),
            "target_forward_return": ret,
            "target_label": label,
        }
        for i in range(1, 17):
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
            "version": "kalman_model_v3_003_btc_tail_test",
            "dataset_version": "test",
            "feature_set": "test",
            "forward_start": forward_start.isoformat(),
            "minimum_feature_coverage": 0.8,
            "candidate_feature_counts": [8],
            "candidate_c": [0.001, 0.01],
            "candidate_class_weight": [None],
            "walk_forward": {
                "initial_train_observations": 250,
                "test_block_observations": 28,
                "horizon_purge_observations": 7,
                "minimum_oof_rows": 180,
            },
            "selection_gate": {
                "minimum_nonoverlap_entries": 8,
            },
            "markets": {
                "BTC": {
                    "symbol": "BTC-USD",
                    "strategy_version": "TEST_BTC_TAIL",
                    "horizon_observations": 7,
                }
            },
        }

    def eval_spec(self, forward_start: pd.Timestamp) -> dict:
        return {
            "forward_start": forward_start.isoformat(),
            "rolling_score_policy": {
                "lookback_observations": 126,
                "minimum_history_observations": 60,
            },
            "policy_selection": {
                "minimum_nonoverlap_entries": 8,
            },
            "costs": {"round_trip_cost_bps": 10.0},
            "promotion_gate": {},
            "markets": {
                "BTC": {
                    "horizon_observations": 7,
                    "candidate_top_fractions": [0.05, 0.10, 0.15],
                }
            },
        }

    def test_tail_candidate_freezes_only_after_joint_gate(self) -> None:
        matrix = self.make_matrix()
        forward_start = pd.Timestamp(matrix.iloc[-8]["as_of"])
        model_spec = self.model_spec(forward_start)
        eval_spec = self.eval_spec(forward_start)

        safe, boundary = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=7,
        )
        oof, _ = expanding_walk_forward_oof(
            safe,
            spec=model_spec,
            horizon=7,
        )
        hp, policy, audit, selected_oof = select_tail_candidate(
            oof,
            model_spec=model_spec,
            evaluation_spec=eval_spec,
            horizon=7,
        )
        self.assertIsNotNone(hp)
        self.assertIsNotNone(policy)
        self.assertIsNotNone(selected_oof)
        self.assertGreater(audit["joint_gate_passing_count"], 0)
        self.assertTrue(audit["pre_forward_gate_pass"])
        self.assertIn(policy.top_fraction, {0.05, 0.10, 0.15})

        artifact = freeze_btc_model(
            safe,
            hyperparameters=hp,
            policy=policy,
            model_spec=model_spec,
            matrix_manifest={"lineage_sha256": "x", "matrix_sha256": "y"},
            training_audit=boundary,
            selection_audit=audit,
        )
        self.assertEqual(artifact["market"], "BTC")
        self.assertEqual(
            artifact["score_semantics"],
            "RANK_SCORE_NOT_CALIBRATED_PROBABILITY",
        )
        self.assertFalse(artifact["trade_execution"])

        reference, ref_audit = build_reference_with_bridge(
            selected_oof=selected_oof,
            matrix=matrix,
            artifact=artifact,
            forward_start=forward_start,
            safe_train_end=pd.Timestamp(safe["as_of"].max()),
        )
        self.assertLess(pd.Timestamp(reference["as_of"].max()), forward_start)
        self.assertEqual(ref_audit["forward_rows_in_reference"], 0)
        self.assertFalse(ref_audit["bridge_outcomes_used"])

    def test_tail_selection_refuses_bad_family(self) -> None:
        n = 260
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        rng = np.random.default_rng(9)
        oof = pd.DataFrame(
            {
                "as_of": dates,
                "anchor_close": np.linspace(100, 120, n),
                "target_forward_return": rng.normal(-0.01, 0.002, n),
                "target_label": np.zeros(n),
                "score": np.linspace(0, 1, n),
            }
        )
        forward_start = pd.Timestamp("2026-09-23")
        model_spec = self.model_spec(forward_start)
        eval_spec = self.eval_spec(forward_start)
        hp, policy, audit, selected = select_tail_candidate(
            {"f8_c0.001_cwnone": oof, "f8_c0.01_cwnone": oof},
            model_spec=model_spec,
            evaluation_spec=eval_spec,
            horizon=7,
        )
        self.assertIsNone(hp)
        self.assertIsNone(policy)
        self.assertIsNone(selected)
        self.assertEqual(audit["joint_gate_passing_count"], 0)
        self.assertFalse(audit["pre_forward_gate_pass"])
        self.assertEqual(
            audit["next_action"],
            "REDESIGN_BTC_TAIL_MODEL_FAMILY",
        )


if __name__ == "__main__":
    unittest.main()
