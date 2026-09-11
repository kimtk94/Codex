from __future__ import annotations

import asyncio
import unittest

from app.config import Settings
from app.main import health
from app.risk import validate_order


class GatewayNoSymbolAllowlistTests(unittest.TestCase):
    def settings(self) -> Settings:
        return Settings(
            trading_enabled=True,
            live_trading_confirm="CONFIRM_LIVE_TRADING",
            live_micro_total_limit_krw=30000,
            max_single_order_krw=5000,
        )

    def test_arbitrary_symbol_is_not_blocked_by_symbol_name(self) -> None:
        decision = validate_order(
            self.settings(),
            "AAPL",
            1000,
            daily_committed_krw=0,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "OK")

    def test_global_single_order_limit_still_applies(self) -> None:
        decision = validate_order(
            self.settings(),
            "AAPL",
            5001,
            daily_committed_krw=0,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "MAX_SINGLE_ORDER_EXCEEDED")

    def test_global_daily_limit_still_applies(self) -> None:
        decision = validate_order(
            self.settings(),
            "MSFT",
            4000,
            daily_committed_krw=27000,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "DAILY_TOTAL_LIMIT_EXCEEDED")

    def test_health_does_not_expose_allowed_symbols(self) -> None:
        payload = asyncio.run(health(self.settings()))
        self.assertNotIn("allowedSymbols", payload)


if __name__ == "__main__":
    unittest.main()
