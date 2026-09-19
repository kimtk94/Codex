from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal
from unittest.mock import patch

from app.config import Settings
from app.main import health
from app.risk import validate_order
from engine.auto_trade import _usd_order_size


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

    def test_fixed_krw_sizing_never_exceeds_5000_target(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AUTO_TRADE_SIZING_MODE": "FIXED_KRW",
                "AUTO_TRADE_ORDER_KRW": "5000",
                "AUTO_TRADE_MIN_ORDER_USD": "1",
                "AUTO_TRADE_MAX_ORDER_USD": "0",
                "AUTO_TRADE_CASH_RESERVE_USD": "0",
            },
            clear=False,
        ):
            amount, detail = _usd_order_size(
                Decimal("100"),
                usd_krw_rate=Decimal("1400"),
            )
        self.assertEqual(amount, Decimal("3.57"))
        self.assertEqual(detail["targetOrderKrw"], "5000")
        self.assertLessEqual(amount * Decimal("1400"), Decimal("5000"))

    def test_health_does_not_expose_allowed_symbols(self) -> None:
        payload = asyncio.run(health(self.settings()))
        self.assertNotIn("allowedSymbols", payload)


if __name__ == "__main__":
    unittest.main()
