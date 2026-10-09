"""Read-only readiness validation must share the LIVE conditional contract."""
from __future__ import annotations
import os
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from decimal import Decimal

from app.config import Settings
from app.readiness import _conditional_contract_readiness, evaluate_live_readiness


class LiveReadinessConditionalContractTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            _env_file=None,
            max_single_order_krw=10000,
            live_micro_total_limit_krw=30000,
        )
        self.env = {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_10000_30000",
            "AUTO_TRADE_CONDITIONAL_TOTAL_KRW": "30000",
            "AUTO_TRADE_ORDER_KRW": "10000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "30000",
        }

    def test_valid_production_10k_30k_contract_passes(self):
        with patch.dict(os.environ, self.env):
            self.assertEqual(
                _conditional_contract_readiness(self.settings, "R5_LIVE_CONDITIONAL"),
                (True, True),
            )

    def test_unknown_confirmation_fails_closed(self):
        with patch.dict(os.environ, {**self.env, "AUTO_TRADE_CONDITIONAL_CONFIRM": "UNKNOWN"}):
            self.assertEqual(
                _conditional_contract_readiness(self.settings, "R5_LIVE_CONDITIONAL"),
                (False, False),
            )

    def test_valid_confirmation_with_inconsistent_order_fails_closed(self):
        with patch.dict(os.environ, {**self.env, "AUTO_TRADE_ORDER_KRW": "20000"}):
            self.assertEqual(
                _conditional_contract_readiness(self.settings, "R5_LIVE_CONDITIONAL"),
                (True, False),
            )

    def test_invalid_exposure_limit_fails_closed(self):
        settings = Settings(
            _env_file=None,
            max_single_order_krw=10000,
            live_micro_total_limit_krw=0,
        )
        with patch.dict(os.environ, self.env):
            self.assertEqual(
                _conditional_contract_readiness(settings, "R5_LIVE_CONDITIONAL"),
                (True, False),
            )

    def test_legacy_20k_confirmation_is_retained(self):
        env = {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_20000",
            "AUTO_TRADE_CONDITIONAL_TOTAL_KRW": "20000",
            "AUTO_TRADE_ORDER_KRW": "20000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "1",
        }
        with patch.dict(os.environ, env):
            self.assertEqual(
                _conditional_contract_readiness(self.settings, "R5_LIVE_CONDITIONAL"),
                (True, True),
            )

    def test_5k_20k_profile_is_retained(self):
        env = {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_5000",
            "AUTO_TRADE_CONDITIONAL_TOTAL_KRW": "20000",
            "AUTO_TRADE_ORDER_KRW": "5000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "15000",
        }
        settings = Settings(
            _env_file=None,
            max_single_order_krw=5000,
            live_micro_total_limit_krw=30000,
        )
        with patch.dict(os.environ, env):
            self.assertEqual(
                _conditional_contract_readiness(settings, "R5_LIVE_CONDITIONAL"),
                (True, True),
            )

    def test_nonconditional_policy_is_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                _conditional_contract_readiness(self.settings, "APPROVED_ONLY"),
                (True, True),
            )


class LiveReadinessFullEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_30k_profile_does_not_show_false_confirmation_missing(self):
        # Exact operational shape: valid 30K profile, ACN already managed,
        # order window closed, and no new signal. No broker/network/DB access.
        from app import readiness

        settings = Settings(
            _env_file=None,
            max_single_order_krw=10000,
            live_micro_total_limit_krw=30000,
            trading_enabled=True,
            live_trading_confirm="CONFIRM_LIVE_TRADING",
        )
        env = {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_10000_30000",
            "AUTO_TRADE_CONDITIONAL_TOTAL_KRW": "30000",
            "AUTO_TRADE_ORDER_KRW": "10000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "30000",
            "AUTO_TRADE_SIGNAL_POLICY": "R5_LIVE_CONDITIONAL",
            "AUTO_TRADE_STRATEGY_VERSION": "R5.1_BASE_HGB",
            "AUTO_TRADE_ENABLED": "true",
            "AUTO_TRADE_EXECUTION_MODE": "LIVE",
            "AUTO_TRADE_REQUIRE_ACCOUNT_FLAT": "false",
        }
        async def holdings():
            return {"items": [{"symbol": "ACN", "quantity": "0.01"}]}
        async def orders(_status):
            return {"orders": []}
        async def buying_power(_currency):
            return {"cashBuyingPower": "100"}
        async def exchange_rate(_a, _b):
            return {"rate": 1400}
        client = SimpleNamespace(
            holdings=holdings, orders=orders, buying_power=buying_power,
            exchange_rate=exchange_rate,
        )
        with (
            patch.dict(os.environ, env),
            patch.object(readiness, "load_signal", return_value=None),
            patch.object(readiness, "ManagedPositionStore") as store,
            patch.object(readiness, "TossClient", return_value=client),
            patch.object(readiness, "us_fractional_order_window",
                         new=AsyncMock(return_value=(False, {}))),
            patch.object(readiness, "_usd_order_size",
                         return_value=(Decimal("7.00"), {"mode": "test"})),
        ):
            store.return_value.active.return_value = [
                {"symbol": "ACN", "state": "OPEN", "remaining_quantity": "0.01"}
            ]
            status = await evaluate_live_readiness(settings)
        assert status["checks"]["conditional_confirmed"] is True
        assert status["checks"]["conditional_contract_valid"] is True
        assert "R5_CONDITIONAL_CONFIRMATION_MISSING" not in status["reason_codes"]
        assert "R5_CONDITIONAL_CONTRACT_INVALID" not in status["reason_codes"]
        assert "NO_ELIGIBLE_SIGNAL" in status["reason_codes"]
        assert "MANAGED_POSITION_ACTIVE" in status["reason_codes"]
        assert "US_ORDER_WINDOW_CLOSED" in status["reason_codes"]
        assert status["execution_attempted"] is False
        assert status["ready"] is False


if __name__ == "__main__":
    unittest.main()
