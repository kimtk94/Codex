from __future__ import annotations

import unittest

from engine.jev_shadow_decision_v1 import (
    build_state,
    deterministic_decision_id,
    normalize_evaluation,
)


class JevShadowDecisionV1Tests(unittest.TestCase):
    def test_state_blinds_symbol_time_and_unknown_payload(self):
        signal = {
            "run_id": "run-1",
            "market": "US",
            "symbol": "AMD",
            "as_of": "2026-10-07T12:00:00+00:00",
            "strategy_version": "R5.1_BASE_HGB",
            "signal": "SHADOW",
            "entry_allowed": False,
            "risk_gate": "PASS",
            "position_state": "FLAT",
            "payload": {
                "probability_up": 0.80,
                "probability_threshold": 0.60,
                "r5_rank": 1,
                "private_or_unknown": "do-not-send",
            },
            "dashboard_top3": [
                {"rank": 1, "symbol": "AMD", "model_score": 0.0008, "universe_size": 93,
                 "score_semantics": "PREDICTED_RELATIVE_RET_4B_NOT_PROBABILITY"},
                {"rank": 2, "symbol": "MSFT", "model_score": 0.0005, "universe_size": 93},
                {"rank": 3, "symbol": "NVDA", "model_score": 0.0004, "universe_size": 93},
            ],
        }
        state = build_state(signal)
        encoded = str(state)
        self.assertNotIn("AMD", encoded)
        self.assertNotIn("MSFT", encoded)
        self.assertNotIn("NVDA", encoded)
        self.assertNotIn("2026-10-07", encoded)
        self.assertNotIn("private_or_unknown", encoded)
        self.assertAlmostEqual(state["signal"]["probability_margin"], 0.20)
        self.assertEqual(state["signal"]["r5_rank"], 1)
        self.assertAlmostEqual(state["signal"]["r5_score"], 0.0008)
        self.assertAlmostEqual(state["signal"]["r5_score_bps"], 8.0)
        self.assertAlmostEqual(state["signal"]["top1_top2_gap"], 0.0003)
        self.assertAlmostEqual(state["signal"]["top1_top2_gap_bps"], 3.0)
        self.assertAlmostEqual(state["signal"]["top1_top3_gap"], 0.0004)
        self.assertAlmostEqual(state["signal"]["top1_top3_gap_bps"], 4.0)
        self.assertEqual(state["signal"]["universe_size"], 93)
        self.assertEqual(state["contract"]["holding_horizon_bars"], 4)
        self.assertEqual(state["contract"]["assumed_total_cost_bps"], 10.0)

    def test_normalizes_choice_boolean_and_score(self):
        result = {
            "model": "typesafe-ai/jev",
            "answers": {
                "entry_support": {
                    "choice": "SUPPORT",
                    "probabilities": {
                        "SUPPORT": 0.7,
                        "NEUTRAL": 0.2,
                        "VETO": 0.1,
                    },
                },
                "positive_ev": {"probability": 0.64},
                "regime": {
                    "choice": "TREND_CONTINUATION",
                    "probabilities": {"TREND_CONTINUATION": 0.6},
                },
                "conviction": {"score": 3.2},
                "addon_support": {"probability": 0.58},
            },
        }
        normalized = normalize_evaluation(result)
        self.assertEqual(normalized["entry_support"], "SUPPORT")
        self.assertAlmostEqual(normalized["positive_ev_probability"], 0.64)
        self.assertEqual(normalized["regime"], "TREND_CONTINUATION")
        self.assertAlmostEqual(normalized["conviction_score"], 3.2)
        self.assertAlmostEqual(normalized["addon_support_probability"], 0.58)

    def test_decision_id_is_deterministic(self):
        a = deterministic_decision_id("run-1", "AMD", "R5.1_BASE_HGB")
        b = deterministic_decision_id("run-1", "AMD", "R5.1_BASE_HGB")
        c = deterministic_decision_id("run-2", "AMD", "R5.1_BASE_HGB")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("jev-"))


if __name__ == "__main__":
    unittest.main()
