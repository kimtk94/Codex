from __future__ import annotations

import unittest
from decimal import Decimal

from engine.us_top6_rebalancer import BasketTarget, build_rebalance_plan


def targets():
    return [
        BasketTarget(1, "GS", 0.9, 100.0),
        BasketTarget(2, "ORCL", 0.8, 100.0),
        BasketTarget(3, "PLTR", 0.7, 100.0),
        BasketTarget(4, "MS", 0.6, 100.0),
        BasketTarget(5, "QCOM", 0.5, 100.0),
        BasketTarget(6, "BA", 0.4, 100.0),
    ]


class UsTop6PlanTests(unittest.TestCase):
    def test_non_target_us_holdings_are_sell_only_first(self):
        holdings = [
            {"symbol": "DE", "marketCountry": "US", "currency": "USD", "quantity": "0.1", "lastPrice": "100"},
            {"symbol": "ORCL", "marketCountry": "US", "currency": "USD", "quantity": "0.01", "lastPrice": "100"},
        ]
        plan = build_rebalance_plan(
            targets=targets(),
            holdings=holdings,
            fx_usd_krw=Decimal("1400"),
            per_symbol_target_krw=5000,
            portfolio_limit_krw=30000,
            min_order_krw=1000,
        )
        self.assertEqual(plan["phase"], "SELL_NON_TARGETS")
        self.assertEqual([x["symbol"] for x in plan["sells"]], ["DE"])
        self.assertEqual(plan["buys"], [])

    def test_non_us_holdings_are_never_sold(self):
        holdings = [
            {"symbol": "005930", "marketCountry": "KR", "currency": "KRW", "quantity": "1", "lastPrice": "100000"},
        ]
        plan = build_rebalance_plan(
            targets=targets(),
            holdings=holdings,
            fx_usd_krw=Decimal("1400"),
            per_symbol_target_krw=5000,
            portfolio_limit_krw=30000,
            min_order_krw=1000,
        )
        self.assertEqual(plan["sells"], [])
        self.assertIn("005930", plan["ignoredNonUsHoldings"])
        self.assertLessEqual(sum(x["orderKrw"] for x in plan["buys"]), 30000)

    def test_empty_us_account_plans_six_5000_buys(self):
        plan = build_rebalance_plan(
            targets=targets(),
            holdings=[],
            fx_usd_krw=Decimal("1400"),
            per_symbol_target_krw=5000,
            portfolio_limit_krw=30000,
            min_order_krw=1000,
        )
        self.assertEqual(plan["phase"], "BUY_UNDERWEIGHTS")
        self.assertEqual(len(plan["buys"]), 6)
        self.assertEqual(sum(x["orderKrw"] for x in plan["buys"]), 30000)
        self.assertTrue(all(x["orderKrw"] <= 5000 for x in plan["buys"]))

    def test_existing_target_value_reduces_topup(self):
        holdings = [
            {
                "symbol": "ORCL",
                "marketCountry": "US",
                "currency": "USD",
                "quantity": "1",
                "marketValue": {"amount": "2"},
            },
        ]
        plan = build_rebalance_plan(
            targets=targets(),
            holdings=holdings,
            fx_usd_krw=Decimal("1400"),
            per_symbol_target_krw=5000,
            portfolio_limit_krw=30000,
            min_order_krw=1000,
        )
        orcl = next(x for x in plan["buys"] if x["symbol"] == "ORCL")
        self.assertEqual(orcl["currentValueKrw"], 2800)
        self.assertEqual(orcl["orderKrw"], 2200)
        self.assertLessEqual(sum(x["orderKrw"] for x in plan["buys"]), 27200)

    def test_configuration_rejects_target_notional_above_total_cap(self):
        with self.assertRaises(ValueError):
            build_rebalance_plan(
                targets=targets(),
                holdings=[],
                fx_usd_krw=Decimal("1400"),
                per_symbol_target_krw=6000,
                portfolio_limit_krw=30000,
                min_order_krw=1000,
            )


if __name__ == "__main__":
    unittest.main()
