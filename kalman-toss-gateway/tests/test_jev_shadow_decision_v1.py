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
        }
        state = build_state(signal)
        encoded = str(state)
        self.assertNotIn("AMD", encoded)
        self.assertNotIn("2026-10-07", encoded)
        self.assertNotIn("private_or_unknown", encoded)
        self.assertAlmostEqual(state["signal"]["probability_margin"], 0.20)

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
