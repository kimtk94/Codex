from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from engine.auto_trade import _usd_order_size


class FixedKrwSizingTests(unittest.TestCase):
    def test_fixed_krw_rounds_down_under_5000(self) -> None:
        env = {
            "AUTO_TRADE_SIZING_MODE": "FIXED_KRW",
            "AUTO_TRADE_ORDER_KRW": "5000",
            "AUTO_TRADE_MIN_ORDER_KRW": "1000",
            "AUTO_TRADE_MAX_ORDER_KRW": "5000",
            "AUTO_TRADE_MIN_ORDER_USD": "1",
            "AUTO_TRADE_MAX_ORDER_USD": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            amount, detail = _usd_order_size(
                Decimal("0"),
                Decimal("10000"),
                Decimal("1344.39"),
                5000,
            )

        self.assertIsNotNone(amount)
        self.assertLessEqual(Decimal(detail["estimatedOrderKrw"]), Decimal("5000"))
        self.assertEqual(detail["targetOrderKrw"], "5000")
        self.assertEqual(detail["sizingMode"], "FIXED_KRW")

    def test_fixed_krw_blocks_when_krw_and_usd_are_insufficient(self) -> None:
        env = {
            "AUTO_TRADE_SIZING_MODE": "FIXED_KRW",
            "AUTO_TRADE_ORDER_KRW": "5000",
            "AUTO_TRADE_MIN_ORDER_KRW": "1000",
            "AUTO_TRADE_MAX_ORDER_KRW": "5000",
            "AUTO_TRADE_MIN_ORDER_USD": "1",
            "AUTO_TRADE_MAX_ORDER_USD": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            amount, detail = _usd_order_size(
                Decimal("0"),
                Decimal("4073"),
                Decimal("1344.39"),
                5000,
            )

        self.assertIsNone(amount)
        self.assertTrue(detail.get("insufficientFunding"))

    def test_hard_single_order_cap_wins_over_env(self) -> None:
        env = {
            "AUTO_TRADE_SIZING_MODE": "FIXED_KRW",
            "AUTO_TRADE_ORDER_KRW": "9000",
            "AUTO_TRADE_MIN_ORDER_KRW": "1000",
            "AUTO_TRADE_MAX_ORDER_KRW": "9000",
            "AUTO_TRADE_MIN_ORDER_USD": "1",
            "AUTO_TRADE_MAX_ORDER_USD": "0",
        }
        with patch.dict(os.environ, env, clear=False):
            amount, detail = _usd_order_size(
                Decimal("100"),
                Decimal("100000"),
                Decimal("1400"),
                5000,
            )

        self.assertIsNotNone(amount)
        self.assertEqual(detail["targetOrderKrw"], "5000")
        self.assertEqual(detail["maxOrderKrw"], "5000")
        self.assertLessEqual(Decimal(detail["estimatedOrderKrw"]), Decimal("5000"))


if __name__ == "__main__":
    unittest.main()
