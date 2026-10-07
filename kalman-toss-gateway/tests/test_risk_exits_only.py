from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.executor import execute_order
from app.risk import validate_order


class RiskExitsOnlyTests(unittest.TestCase):
    def test_buy_is_blocked_before_broker_when_entry_gate_is_false(self) -> None:
        request = SimpleNamespace(
            client_order_id="test-buy-disabled",
            symbol="AAPL",
            side="BUY",
            order_type="MARKET",
            time_in_force="DAY",
            quantity=None,
            order_amount="1",
            price=None,
        )
        with patch.dict(os.environ, {"AUTO_TRADE_ENTRY_ENABLED": "false"}, clear=False):
            result = asyncio.run(execute_order(object(), request))
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "ENTRY_DISABLED_BY_COST_GATE")
        self.assertFalse(result["executionAttempted"])

    def test_risk_reducing_exit_remains_allowed_with_live_gate(self) -> None:
        settings = Settings(
            trading_enabled=True,
            live_trading_confirm="CONFIRM_LIVE_TRADING",
            live_micro_total_limit_krw=0,
            max_single_order_krw=5000,
        )
        decision = validate_order(
            settings,
            "AAPL",
            500_000,
            daily_committed_krw=999_999,
            risk_reducing_exit=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "OK_RISK_REDUCING_EXIT")


if __name__ == "__main__":
    unittest.main()
