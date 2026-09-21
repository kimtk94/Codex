from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.config import Settings
from app.executor import TradeLedger
from app.main import health
from app.risk import validate_order
from engine.auto_trade import _effective_signal_as_of, _signal_bar_minutes, _usd_order_size


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

    def test_positive_daily_limit_still_applies_when_configured(self) -> None:
        decision = validate_order(
            self.settings(),
            "MSFT",
            4000,
            daily_committed_krw=27000,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "DAILY_TOTAL_LIMIT_EXCEEDED")

    def test_zero_daily_limit_means_balance_driven_no_fixed_daily_cap(self) -> None:
        settings = Settings(
            trading_enabled=True,
            live_trading_confirm="CONFIRM_LIVE_TRADING",
            live_micro_total_limit_krw=0,
            max_single_order_krw=5000,
        )
        decision = validate_order(
            settings,
            "MSFT",
            5000,
            daily_committed_krw=250000,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "OK")

    def test_trade_ledger_zero_daily_limit_allows_repeated_5000_buys(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger = TradeLedger(Path(tmp) / "trading.sqlite3")
            for i in range(10):
                ok, reason, used = ledger.reserve(
                    f"order-{i}",
                    f"SYM{i}",
                    "BUY",
                    5000,
                    0,
                )
                self.assertTrue(ok)
                self.assertEqual(reason, "OK")
                ledger.finish(f"order-{i}", "SUBMITTED", f"toss-{i}")
            self.assertEqual(ledger.daily_committed(), 50000)

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

    def test_r5_1_signal_freshness_uses_bar_completion(self) -> None:
        as_of = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
        with patch.dict(
            "os.environ",
            {"AUTO_TRADE_SIGNAL_BAR_MINUTES": "60"},
            clear=False,
        ):
            self.assertEqual(_signal_bar_minutes("R5.1_BASE_HGB"), 60)
            effective = _effective_signal_as_of(as_of, "R5.1_BASE_HGB")
        self.assertEqual(
            effective,
            datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc),
        )

    def test_r5_1_rejects_wrong_bar_duration(self) -> None:
        with patch.dict(
            "os.environ",
            {"AUTO_TRADE_SIGNAL_BAR_MINUTES": "0"},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires AUTO_TRADE_SIGNAL_BAR_MINUTES=60"):
                _signal_bar_minutes("R5.1_BASE_HGB")

    def test_health_does_not_expose_allowed_symbols(self) -> None:
        payload = asyncio.run(health(self.settings()))
        self.assertNotIn("allowedSymbols", payload)


if __name__ == "__main__":
    unittest.main()
