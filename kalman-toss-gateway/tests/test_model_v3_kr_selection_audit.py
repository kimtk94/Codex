from __future__ import annotations

import unittest

from research.model_v3.audit_kr_selection import summarize


class ModelV3KRAuditTests(unittest.TestCase):
    def test_detects_joint_gate_candidate(self) -> None:
        payload = {
            "selected_candidate_id": "bad",
            "selected_policy": {"top_fraction": 0.2},
            "candidate_policy_results": [
                {
                    "candidate_id": "bad",
                    "hyperparameters": {"feature_count": 8, "C": 0.1},
                    "top_fraction": 0.2,
                    "selection_eligible": True,
                    "selection_checks": {
                        "minimum_oof_rows": True,
                        "minimum_nonoverlap_entries": True,
                    },
                    "probability_metrics": {
                        "rows": 400,
                        "roc_auc": 0.43,
                        "brier": 0.33,
                        "log_loss": 0.89,
                    },
                    "strategy_metrics": {
                        "nonoverlap_selected_rows": 22,
                        "nonoverlap_incremental_alpha_mean_net": 0.005,
                        "nonoverlap_win_rate_lift": -0.05,
                        "nonoverlap_selected_net": {
                            "mean": 0.02,
                            "compounded_return": 0.5,
                        },
                    },
                },
                {
                    "candidate_id": "good",
                    "hyperparameters": {"feature_count": 16, "C": 0.01},
                    "top_fraction": 0.3,
                    "selection_eligible": True,
                    "selection_checks": {
                        "minimum_oof_rows": True,
                        "minimum_nonoverlap_entries": True,
                    },
                    "probability_metrics": {
                        "rows": 400,
                        "roc_auc": 0.53,
                        "brier": 0.24,
                        "log_loss": 0.68,
                    },
                    "strategy_metrics": {
                        "nonoverlap_selected_rows": 25,
                        "nonoverlap_incremental_alpha_mean_net": 0.003,
                        "nonoverlap_win_rate_lift": 0.04,
                        "nonoverlap_selected_net": {
                            "mean": 0.018,
                            "compounded_return": 0.4,
                        },
                    },
                },
            ],
        }
        report = summarize(payload)
        self.assertEqual(report["joint_gate_passing_count"], 1)
        self.assertEqual(
            report["joint_gate_passing_top"][0]["candidate_id"], "good"
        )
        self.assertEqual(
            report["next_action"],
            "V3_004_JOINT_GATE_CANDIDATE_AVAILABLE",
        )
        self.assertFalse(
            report["selected_candidate"]["joint_gate_pass"]
        )

    def test_redesign_when_no_joint_gate_candidate(self) -> None:
        payload = {
            "selected_candidate_id": "only",
            "selected_policy": {"top_fraction": 0.2},
            "candidate_policy_results": [
                {
                    "candidate_id": "only",
                    "hyperparameters": {"feature_count": 8, "C": 0.1},
                    "top_fraction": 0.2,
                    "selection_eligible": True,
                    "selection_checks": {},
                    "probability_metrics": {"rows": 400, "roc_auc": 0.45},
                    "strategy_metrics": {
                        "nonoverlap_selected_rows": 20,
                        "nonoverlap_incremental_alpha_mean_net": 0.004,
                        "nonoverlap_win_rate_lift": -0.02,
                        "nonoverlap_selected_net": {
                            "mean": 0.01,
                            "compounded_return": 0.2,
                        },
                    },
                }
            ],
        }
        report = summarize(payload)
        self.assertEqual(report["joint_gate_passing_count"], 0)
        self.assertEqual(
            report["next_action"], "REDESIGN_KR_MODEL_FAMILY"
        )


if __name__ == "__main__":
    unittest.main()
