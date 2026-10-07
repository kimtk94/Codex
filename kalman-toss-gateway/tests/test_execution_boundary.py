from __future__ import annotations

import unittest

from engine.execution_boundary import (
    AUTO_TRADE_ENTRY_POLICIES,
    CONDITIONAL_CONFIRM_TOKENS,
    LIVE_R5_STRATEGY,
    READINESS_POLICIES,
    is_r5_2_research_strategy,
    r5_live_strategy_locked,
)


class ExecutionBoundaryTests(unittest.TestCase):
    def test_r5_live_top1_accepts_only_frozen_r5_1(self) -> None:
        self.assertTrue(r5_live_strategy_locked("R5_LIVE_TOP1", LIVE_R5_STRATEGY))
        self.assertFalse(r5_live_strategy_locked("R5_LIVE_TOP1", "R5.2_COST_AWARE_RESEARCH_V1"))

    def test_r5_live_conditional_accepts_only_frozen_r5_1(self) -> None:
        self.assertTrue(r5_live_strategy_locked("R5_LIVE_CONDITIONAL", LIVE_R5_STRATEGY))
        self.assertFalse(r5_live_strategy_locked("R5_LIVE_CONDITIONAL", "R5.2_COST_AWARE_RESEARCH_V1"))

    def test_non_r5_live_policy_is_not_reclassified_here(self) -> None:
        self.assertTrue(r5_live_strategy_locked("APPROVED_ONLY", "OTHER_STRATEGY"))

    def test_policy_sets_match_executor_and_readiness_roles(self) -> None:
        self.assertIn("R5_LIVE_TOP1", AUTO_TRADE_ENTRY_POLICIES)
        self.assertNotIn("R5_LIVE_CONDITIONAL", AUTO_TRADE_ENTRY_POLICIES)
        self.assertIn("R5_LIVE_TOP1", READINESS_POLICIES)
        self.assertIn("R5_LIVE_CONDITIONAL", READINESS_POLICIES)

    def test_both_conditional_execution_contracts_are_visible_to_readiness(self) -> None:
        self.assertEqual(
            CONDITIONAL_CONFIRM_TOKENS,
            {
                "CONFIRM_R5_LIVE_CONDITIONAL_20000",
                "CONFIRM_R5_LIVE_CONDITIONAL_5000",
            },
        )

    def test_r5_2_is_classified_research_only_by_name(self) -> None:
        self.assertTrue(is_r5_2_research_strategy("R5.2_COST_AWARE_RESEARCH_V1"))
        self.assertTrue(is_r5_2_research_strategy("R5_2_COST_AWARE_RESEARCH_V1"))
        self.assertFalse(is_r5_2_research_strategy("R5.1_BASE_HGB"))


if __name__ == "__main__":
    unittest.main()
