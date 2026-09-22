from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.model_v3.shadow_tracker import build_summary


class ModelV3ShadowTrackerTests(unittest.TestCase):
    def write_report(self, root: Path, rel: str, market: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "READY",
            "mode": "TRACK_EXISTING_FROZEN_MODEL",
            "model_version": f"model_{market.lower()}",
            "strategy_version": f"strategy_{market.lower()}",
            "forward_start": "2026-09-23T00:00:00",
            "matrix_as_of": "2026-09-23T00:00:00",
            "pre_forward_gate_pass": True,
            "promotion_eligible": False,
            "locked_policy": {"top_fraction": 0.2},
            "target_hurdle": 0.005 if market == "US" else None,
            "score_semantics": "RANK_SCORE",
            "pre_forward_selection": {
                "selected_oof_strategy_metrics": {
                    "nonoverlap_selected_rows": 12,
                    "nonoverlap_incremental_alpha_mean_net": 0.01,
                    "nonoverlap_win_rate_lift": 0.05,
                    "nonoverlap_selected_net": {
                        "mean": 0.02,
                        "win_rate": 0.70,
                        "compounded_return": 0.30,
                    },
                }
            },
            "forward_gate": {
                "status": "TRACKING_INSUFFICIENT_FORWARD_HISTORY",
                "forward_observations": 1,
                "nonoverlap_incremental_alpha_mean_net": None,
                "nonoverlap_win_rate_lift": None,
                "nonoverlap_selected_net": {
                    "rows": 0,
                    "mean": None,
                    "win_rate": None,
                    "compounded_return": None,
                    "max_drawdown": None,
                },
                "checks": {
                    "minimum_forward_observations": False,
                },
            },
            "current_shadow_signal": {
                "status": "READY",
                "as_of": "2026-09-23T00:00:00",
                "score": 0.7,
                "score_cutoff": 0.6,
                "top_fraction": 0.2,
                "policy_ready": True,
                "forward_era": True,
                "shadow_entry": market == "BTC",
                "live_execution": False,
            },
            "forward_ledgers": {
                "append_only": True,
                "score_rows": 1,
                "outcome_rows": 0,
            },
            "research_only": True,
            "shadow_only": True,
            "production_write": False,
            "neon_write": False,
            "trade_execution": False,
            "retrained_existing_frozen_model": False,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_ready_summary_and_shadow_entry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_report(
                root,
                "Market_Model_V3_004_KR_JointGate/frozen/latest.json",
                "KR",
            )
            self.write_report(
                root,
                "Market_Model_V3_003_BTC_Tail/frozen/latest.json",
                "BTC",
            )
            self.write_report(
                root,
                "Market_Model_V3_003_US_Hurdle/frozen/latest.json",
                "US",
            )
            summary = build_summary(root)
            self.assertEqual(summary["status"], "READY")
            self.assertTrue(summary["all_models_present"])
            self.assertTrue(summary["safety_pass"])
            self.assertTrue(summary["any_shadow_entry"])
            self.assertFalse(summary["trade_execution"])
            self.assertEqual(summary["forward_observations"]["BTC"], 1)
            self.assertTrue(
                summary["markets"]["BTC"]["signal"]["shadow_entry"]
            )

    def test_missing_model_forces_attention(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_report(
                root,
                "Market_Model_V3_004_KR_JointGate/frozen/latest.json",
                "KR",
            )
            summary = build_summary(root)
            self.assertEqual(summary["status"], "ATTENTION")
            self.assertFalse(summary["all_models_present"])
            self.assertFalse(summary["safety_pass"])

    def test_safety_violation_forces_attention(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, market in [
                ("Market_Model_V3_004_KR_JointGate/frozen/latest.json", "KR"),
                ("Market_Model_V3_003_BTC_Tail/frozen/latest.json", "BTC"),
                ("Market_Model_V3_003_US_Hurdle/frozen/latest.json", "US"),
            ]:
                self.write_report(root, rel, market)

            btc = root / "Market_Model_V3_003_BTC_Tail/frozen/latest.json"
            payload = json.loads(btc.read_text())
            payload["trade_execution"] = True
            btc.write_text(json.dumps(payload), encoding="utf-8")

            summary = build_summary(root)
            self.assertEqual(summary["status"], "ATTENTION")
            self.assertFalse(summary["safety_pass"])


if __name__ == "__main__":
    unittest.main()
