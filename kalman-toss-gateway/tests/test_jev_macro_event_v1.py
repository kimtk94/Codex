from __future__ import annotations

import unittest

from engine.jev_macro_event_v1 import (
    EVAL_VERSION,
    build_state,
    macro_is_informative,
    normalize,
)


class JevMacroEventV13Tests(unittest.TestCase):
    def test_blocked_macro_is_not_informative(self):
        ready, sources = macro_is_informative({
            "macro_event_signal_ready": False,
            "macro_event_free_reaction_ready": False,
            "us2y_change_bps_1d": 1.0,
        })
        self.assertFalse(ready)
        self.assertEqual(sources, [])

    def test_bea_gdp_title_with_state_pce_stays_gdp(self):
        from engine.jev_macro_event_v1 import official_event_family
        title = "GDP, (Third Estimate), Industries, Corporate Profits, State GDP, and State Personal Income, 2nd Quarter 2026; State PCE, 2025"
        self.assertEqual(official_event_family("bea_releases", title), "GDP")

    def test_event_reaction_is_informative(self):
        ready, sources = macro_is_informative({
            "macro_event_signal_ready": False,
            "us2y_event_reaction_bps": 11.0,
        })
        self.assertTrue(ready)
        self.assertIn("us2y_event_reaction_bps", sources)

    def test_first_seen_safe_official_event_can_activate_challenger(self):
        state = build_state(
            {
                "coverage_confidence": 0.65,
                "features": {
                    "macro_event_family": "OTHER",
                    "macro_event_signal_ready": False,
                    "macro_event_free_reaction_ready": False,
                },
            },
            {
                "source": "bls_employment",
                "title": "Payroll employment increased modestly; unemployment rate changed little",
                "age_minutes": 56.0,
            },
        )
        self.assertTrue(state["macro"]["event_informative"])
        self.assertIn("official_macro_event_first_seen_safe", state["macro"]["readiness_sources"])
        self.assertEqual(state["macro"]["official_event"]["family"], "NFP")
        self.assertEqual(
            state["macro"]["official_event"]["availability_semantics"],
            "MAX_PROVIDER_AVAILABLE_FIRST_SEEN",
        )

    def test_state_excludes_r51_and_execution_features(self):
        state = build_state({
            "coverage_confidence": 0.9,
            "features": {
                "macro_event_family": "CPI",
                "macro_event_signal_ready": True,
                "us_priority_surprise_index": 1.3,
                "us2y_event_reaction_bps": 12.0,
                "fed_policy_repricing_bps": 8.0,
                "r5_score": 0.001,
                "position_weight": 1.0,
                "risk_gate": "PASS",
                "symbol": "AMD",
                "as_of": "2026-10-07T14:30:00Z",
            },
        })
        encoded = str(state)
        self.assertTrue(state["macro"]["event_informative"])
        self.assertNotIn("r5_score", encoded)
        self.assertNotIn("position_weight", encoded)
        self.assertNotIn("risk_gate", encoded)
        self.assertNotIn("AMD", encoded)
        self.assertNotIn("2026-10-07", encoded)
        self.assertFalse(state["contract"]["live_execution_authority"])

    def test_normalize(self):
        raw = {
            "model": "typesafe-ai/jev",
            "answers": {
                "macro_entry_support": {
                    "choice": "VETO",
                    "probabilities": {"SUPPORT": 0.1, "NEUTRAL": 0.2, "VETO": 0.7},
                },
                "macro_regime": {
                    "choice": "HAWKISH_TIGHTENING",
                    "probabilities": {"HAWKISH_TIGHTENING": 0.8},
                },
                "macro_materiality": {"score": 3.4},
            },
            "usage": {"inputTokens": 100},
        }
        out = normalize(raw)
        self.assertEqual(out["entry_support"], "VETO")
        self.assertAlmostEqual(out["entry_support_probabilities"]["VETO"], 0.7)
        self.assertEqual(out["regime"], "HAWKISH_TIGHTENING")
        self.assertAlmostEqual(out["conviction_score"], 3.4)
        self.assertEqual(EVAL_VERSION, "jev-macro-event-v1.3.2")


if __name__ == "__main__":
    unittest.main()
