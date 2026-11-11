from __future__ import annotations

import unittest
from datetime import datetime, timezone

from research.jev_v14_forward_shadow import (
    EVAL_VERSION,
    apply_gate,
    build_state,
    event_family,
    stable_id,
)

UTC = timezone.utc


class JevV14ForwardShadowTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "decision_gate": {
                "min_evidence_probability": 0.70,
                "min_execution_timing_confidence": 0.65,
                "fallback_action": "NOW",
            },
            "rate_proxy": {
                "calibration_target": "DGS2_CHG_1_BP",
                "calibration_sample_n": 2417,
                "calibration_r2": 0.8518366911673452,
                "calibration_correlation": -0.9229499938606344,
                "bp_per_plus_1pct_proxy_return": -49.80568987492392,
                "calibration_window": "2017-01-03_to_2026-09-10",
                "quality": "RESEARCH_EMPIRICAL_DAILY_MAPPING_NOT_DIRECT_INTRADAY_YIELD",
            },
        }

    def test_event_family(self):
        self.assertEqual(event_family("Nonfarm Payrolls (Employment Situation)"), "NFP")
        self.assertEqual(event_family("Personal Income and Outlays (PCE)"), "PCE")
        self.assertEqual(event_family("GDP (Third Estimate), State PCE"), "GDP")
        self.assertEqual(event_family("Initial Jobless Claims"), "JOBLESS_CLAIMS")

    def test_gate_defaults_to_now_when_weak(self):
        passed, action = apply_gate(
            self.config,
            {
                "evidence_sufficient_probability": 0.69,
                "execution_timing_confidence": 0.99,
                "execution_timing": "WAIT_2",
            },
        )
        self.assertFalse(passed)
        self.assertEqual(action, "NOW")

    def test_gate_allows_high_confidence_action(self):
        passed, action = apply_gate(
            self.config,
            {
                "evidence_sufficient_probability": 0.91,
                "execution_timing_confidence": 0.80,
                "execution_timing": "WAIT_1",
            },
        )
        self.assertTrue(passed)
        self.assertEqual(action, "WAIT_1")

    def test_state_blinds_candidate_identity_and_absolute_time(self):
        event = {
            "event_family": "NFP",
            "actual": 29.0,
            "previous": 133.0,
            "unit": "thousands",
            "scheduled_at": datetime(2026, 10, 2, 12, 30, tzinfo=UTC),
            "first_observed_at": datetime(2026, 10, 2, 12, 34, tzinfo=UTC),
        }
        state = build_state(
            self.config,
            [event],
            {
                "5m": {
                    "shy_return_pct": 0.12,
                    "implied_us2y_reaction_bps": -6.1,
                    "proxy": "SHY",
                }
            },
            {"market_beta_eqw_20d": 1.1, "realized_vol_bar_20d": 0.01},
            datetime(2026, 10, 2, 13, 30, tzinfo=UTC),
        )
        encoded = str(state)
        self.assertNotIn("AMD", encoded)
        self.assertNotIn("run_id", encoded)
        self.assertNotIn("2026-10-02", encoded)
        self.assertFalse(state["contract"]["live_execution_authority"])
        self.assertEqual(EVAL_VERSION, "jev-v1.4-forward-shadow-v1")

    def test_stable_id(self):
        self.assertEqual(stable_id("x-", "a", 1), stable_id("x-", "a", 1))
        self.assertNotEqual(stable_id("x-", "a", 1), stable_id("x-", "a", 2))


if __name__ == "__main__":
    unittest.main()
