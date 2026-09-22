from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.model_v3.kr_candidate import (
    expanding_walk_forward_oof,
    freeze_model,
    safe_pre_forward,
)
from research.model_v3.kr_joint_gate_candidate import (
    build_reference_with_bridge,
    fixed_selection,
)


class ModelV3004KRJointGateTests(unittest.TestCase):
    def make_matrix(self, n: int = 560) -> pd.DataFrame:
        rng = np.random.default_rng(4004)
        dates = pd.bdate_range("2024-07-01", periods=n)
        f1 = rng.normal(size=n)
        f2 = rng.normal(size=n)
        latent = 1.1 * f1 - 0.25 * f2 + rng.normal(0, 0.5, size=n)
        label = (latent > 0).astype(float)
        ret = np.where(label > 0, 0.02, -0.012) + rng.normal(0, 0.003, size=n)
        data = {
            "as_of": dates,
            "anchor_close": 100 * np.cumprod(1 + rng.normal(0.0004, 0.006, size=n)),
            "target_forward_return": ret,
            "target_label": label,
        }
        for i in range(1, 17):
            if i == 1:
                data[f"f{i}"] = f1
            elif i == 2:
                data[f"f{i}"] = f2
            else:
                data[f"f{i}"] = rng.normal(size=n)
        return pd.DataFrame(data)

    def model_spec(self, forward_start: pd.Timestamp) -> dict:
        return {
            "version": "kalman_model_v3_004_kr_joint_gate_test",
            "dataset_version": "test",
            "feature_set": "test",
            "forward_start": forward_start.isoformat(),
            "methodology_status": "POST_V3_003_OOF_AUDIT_PRE_FORWARD_FIXED",
            "forward_data_used_for_model_selection": False,
            "minimum_feature_coverage": 0.8,
            "candidate_feature_counts": [8],
            "candidate_c": [0.001],
            "candidate_class_weight": [None],
            "fixed_joint_gate_policy": {
                "candidate_id": "f8_c0.001_cwnone",
                "feature_count": 8,
                "C": 0.001,
                "class_weight": None,
                "top_fraction": 0.2,
                "selection_origin": "TEST",
                "expected_minimum_nonoverlap_entries": 8,
            },
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
            "markets": {"KR": {"horizon_observations": 5}},
        }

    def test_fixed_candidate_and_bridge_are_pre_forward_only(self) -> None:
        matrix = self.make_matrix()
        forward_start = pd.Timestamp(matrix.iloc[-8]["as_of"])
        model_spec = self.model_spec(forward_start)
        evaluation_spec = self.eval_spec(forward_start)

        safe, boundary = safe_pre_forward(
            matrix,
            forward_start=forward_start,
            horizon=5,
        )
        oof, _ = expanding_walk_forward_oof(
            safe,
            spec=model_spec,
            horizon=5,
        )
        hp, policy, selection, selected_oof = fixed_selection(
            oof,
            model_spec=model_spec,
            evaluation_spec=evaluation_spec,
            horizon=5,
        )
        self.assertEqual(selection["selected_candidate_id"], "f8_c0.001_cwnone")
        self.assertEqual(policy.top_fraction, 0.2)
        self.assertTrue(selection["pre_forward_gate_pass"])
        self.assertEqual(selection["forward_rows_used_for_selection"], 0)

        artifact = freeze_model(
            safe,
            hyperparameters=hp,
            policy=policy,
            model_spec=model_spec,
            matrix_manifest={"lineage_sha256": "x", "matrix_sha256": "y"},
            training_audit=boundary,
            selection_audit=selection,
        )
        reference, audit = build_reference_with_bridge(
            selected_oof=selected_oof,
            matrix=matrix,
            artifact=artifact,
            forward_start=forward_start,
            safe_train_end=pd.Timestamp(safe["as_of"].max()),
        )
        self.assertLess(pd.Timestamp(reference["as_of"].max()), forward_start)
        self.assertGreater(audit["bridge_rows"], 0)
        self.assertEqual(audit["forward_rows_in_reference"], 0)
        self.assertFalse(audit["bridge_outcomes_used"])

        bridge = reference.loc[
            reference["reference_source"] == "FROZEN_MODEL_PRE_FORWARD_BRIDGE"
        ]
        self.assertTrue(bridge["target_forward_return"].isna().all())
        self.assertTrue(bridge["target_label"].isna().all())


if __name__ == "__main__":
    unittest.main()
