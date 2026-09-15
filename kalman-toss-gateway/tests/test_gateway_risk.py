from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.main import health, shadow_bakeoff
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

    def test_manual_live_gate_is_independent_from_auto_gate(self) -> None:
        settings = Settings(
            trading_enabled=False,
            live_trading_confirm="",
            manual_trading_enabled=True,
            manual_trading_confirm="CONFIRM_MANUAL_TRADING",
            live_micro_total_limit_krw=30000,
            max_single_order_krw=5000,
        )
        manual = validate_order(
            settings,
            "AAPL",
            1000,
            execution_channel="MANUAL",
        )
        automated = validate_order(
            settings,
            "AAPL",
            1000,
            execution_channel="AUTO",
        )
        self.assertTrue(manual.allowed)
        self.assertEqual(manual.reason, "OK")
        self.assertFalse(automated.allowed)
        self.assertEqual(automated.reason, "TRADING_DISABLED")
        self.assertTrue(settings.manual_live_gate_open)
        self.assertFalse(settings.live_gate_open)

    def test_health_does_not_expose_allowed_symbols(self) -> None:
        payload = asyncio.run(health(self.settings()))
        self.assertNotIn("allowedSymbols", payload)

    def test_shadow_bakeoff_route_is_read_only_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bakeoff_status.json"
            path.write_text(
                json.dumps(
                    {
                        "status": "READY",
                        "experiment": "FORWARD_SHADOW_BAKEOFF_V1",
                        "tracking_status": "TRACKING",
                        "seed_end": "2026-09-11T00:00:00+00:00",
                        "latest_as_of": "2026-09-14T00:00:00+00:00",
                        "updated_at": "2026-09-15T09:00:00+00:00",
                        "post_seed_return_rows": 2,
                        "has_post_seed_signal": True,
                        "signal_status": {
                            "US": {
                                "market": "US",
                                "symbol": "SPY",
                                "as_of": "2026-09-14T00:00:00+00:00",
                                "signal": "BUY",
                                "entry_allowed": True,
                                "probability": 0.9,
                                "probability_threshold": 0.6,
                                "missing_feature_ratio": 0.03,
                                "selected_feature_count": 28,
                                "research_only": True,
                                "shadow_only": True,
                                "live_execution": False,
                                "toss_execution": False,
                                "selected_features": ["secret-ish diagnostic"],
                            }
                        },
                        "forward_ranking": [
                            {
                                "strategy": "A_EQUAL_WEIGHT",
                                "status": "READY",
                                "forward_rank": 0,
                                "total_return": 0.01,
                                "sharpe": 1.2,
                                "max_drawdown": -0.02,
                                "latest_target": {"US": 0.33, "KR": 0.33, "BTC": 0.34},
                            }
                        ],
                        "invariants": {
                            "file_only": True,
                            "production_write": False,
                            "neon_write": False,
                            "toss_execution": False,
                            "live_execution": False,
                            "auto_trade_visible": False,
                            "dashboard_snapshot_created": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            settings = self.settings().model_copy(
                update={"shadow_bakeoff_status": str(path)}
            )
            payload = asyncio.run(shadow_bakeoff(settings))
            self.assertEqual(payload["status"], "READY")
            self.assertTrue(payload["invariants"]["read_only"])
            self.assertFalse(payload["invariants"]["trade_execution"])
            self.assertNotIn("selected_features", payload["signals"]["US"])
            self.assertEqual(payload["signals"]["US"]["signal"], "BUY")


if __name__ == "__main__":
    unittest.main()
