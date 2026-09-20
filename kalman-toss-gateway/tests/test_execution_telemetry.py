from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile
from decimal import Decimal

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.executor import TradeLedger, _quote_telemetry
from app.toss_client import TossClient
from engine.position_manager import _broker_order_telemetry
from engine.execution_telemetry_sync import _broker_orders, _fetch_order_with_bounded_429_retry
from engine.trade_mirror import _execution_quality, _round_trip_quality


def test_toss_client_captures_rate_limit_response_metadata():
    client = TossClient(Settings())
    request = httpx.Request("GET", "https://openapi.tossinvest.com/api/v1/prices?symbols=AAPL")
    response = httpx.Response(
        200,
        request=request,
        headers={
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": "7",
            "X-RateLimit-Reset": "1",
            "Retry-After": "2",
            "X-Request-Id": "req-123",
        },
        json={"result": []},
    )
    assert client._response_json(response) == {"result": []}
    assert client.last_response_meta["endpoint"] == "/api/v1/prices"
    assert client.last_response_meta["rate_limit_limit"] == 10
    assert client.last_response_meta["rate_limit_remaining"] == 7
    assert client.last_response_meta["rate_limit_reset_seconds"] == 1
    assert client.last_response_meta["retry_after_seconds"] == 2
    assert client.last_response_meta["request_id"] == "req-123"


def test_quote_telemetry_uses_executable_touch_and_spread():
    q = _quote_telemetry(
        {
            "result": {
                "timestamp": "2026-09-21T09:30:00+09:00",
                "currency": "USD",
                "asks": [{"price": "101"}, {"price": "100.5"}],
                "bids": [{"price": "99.5"}, {"price": "100"}],
            }
        }
    )
    assert q["best_ask"] == "100.5"
    assert q["best_bid"] == "100"
    assert Decimal(q["mid"]) == Decimal("100.25")
    assert abs(Decimal(q["spread_bps"]) - Decimal("49.87531172069825436408977556")) < Decimal("1e-20")


def test_trade_ledger_migrates_and_merges_telemetry_json():
    with tempfile.TemporaryDirectory() as td:
        ledger = TradeLedger(pathlib.Path(td) / "trading.sqlite3")
        ok, reason, _ = ledger.reserve("cid-1", "AAPL", "BUY", 5000, 30000)
        assert ok is True
        assert reason == "OK"
        ledger.patch_telemetry("cid-1", {"pretrade_quote": {"best_ask": "100"}})
        ledger.patch_telemetry("cid-1", {"submit": {"http_latency_ms": 42.5}})
        row = ledger.get("cid-1")
        payload = json.loads(row["telemetry_json"])
        assert payload["pretrade_quote"]["best_ask"] == "100"
        assert payload["submit"]["http_latency_ms"] == 42.5


def test_broker_order_telemetry_captures_cost_and_fill_latency():
    t = _broker_order_telemetry(
        {
            "orderId": "order-1",
            "status": "FILLED",
            "currency": "USD",
            "orderedAt": "2026-09-21T09:30:00+09:00",
            "execution": {
                "filledQuantity": "1",
                "averageFilledPrice": "100.25",
                "filledAmount": "100.25",
                "commission": "0.10",
                "tax": "0",
                "filledAt": "2026-09-21T09:30:02.500+09:00",
                "settlementDate": None,
            },
        },
        {"rate_limit_remaining": 8},
    )
    assert t["status"] == "FILLED"
    assert t["commission"] == "0.10"
    assert t["tax"] == "0"
    assert t["broker_fill_latency_ms"] == 2500.0
    assert t["response_meta"]["rate_limit_remaining"] == 8


def test_execution_quality_measures_touch_slippage_and_cost():
    q = _execution_quality(
        "BUY",
        "100.60",
        {
            "pretrade_quote": {
                "currency": "USD",
                "best_bid": "100.00",
                "best_ask": "100.50",
                "spread_bps": "49.8753117207",
            },
            "submit": {
                "http_latency_ms": 37.2,
                "response_meta": {"rate_limit_remaining": 6},
            },
            "broker_order": {
                "currency": "USD",
                "filled_amount": "100.60",
                "commission": "0.10",
                "tax": "0",
                "broker_fill_latency_ms": 1200.0,
            },
        },
    )
    expected_slippage = float(Decimal("0.10") / Decimal("100.50") * Decimal("10000"))
    assert abs(q["slippage_bps"] - expected_slippage) < 1e-9
    assert abs(q["cost_bps"] - float(Decimal("0.10") / Decimal("100.60") * Decimal("10000"))) < 1e-9
    assert q["submit_http_latency_ms"] == 37.2
    assert q["broker_fill_latency_ms"] == 1200.0
    assert q["rate_limit_remaining"] == 6


def test_round_trip_quality_uses_actual_broker_costs():
    q = _round_trip_quality(
        {"filled_amount": 100.0, "commission": 0.1, "tax": 0.0},
        {"filled_amount": 110.0, "commission": 0.1, "tax": 0.0},
    )
    assert abs(q["gross_return"] - 0.10) < 1e-12
    expected_net = (Decimal("109.9") / Decimal("100.1")) - Decimal("1")
    assert abs(q["net_return"] - float(expected_net)) < 1e-12
    assert abs(q["round_trip_cost_bps"] - 20.0) < 1e-12


def test_broker_orders_reads_only_rows_with_toss_order_id():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "trading.sqlite3"
        ledger = TradeLedger(path)
        ok, _, _ = ledger.reserve("cid-a", "AAPL", "BUY", 5000, 30000)
        assert ok
        ledger.finish("cid-a", "SUBMITTED", "order-a")
        ok, _, _ = ledger.reserve("cid-b", "MSFT", "BUY", 5000, 30000)
        assert ok
        rows = _broker_orders(path, 10)
        assert [row["client_order_id"] for row in rows] == ["cid-a"]
        assert rows[0]["toss_order_id"] == "order-a"


def test_429_retry_is_bounded_and_read_only():
    request = httpx.Request("GET", "https://openapi.tossinvest.com/api/v1/orders/order-1")
    response = httpx.Response(
        429,
        request=request,
        headers={"Retry-After": "0"},
        json={"error": {"code": "RATE_LIMIT"}},
    )

    class FakeClient:
        def __init__(self):
            self.calls = 0
            self.last_response_meta = {"retry_after_seconds": 0}

        async def order(self, order_id):
            self.calls += 1
            if self.calls == 1:
                raise httpx.HTTPStatusError("429", request=request, response=response)
            return {"result": {"orderId": order_id, "status": "FILLED", "execution": {}}}

    client = FakeClient()
    out = asyncio.run(_fetch_order_with_bounded_429_retry(client, "order-1"))
    assert out["orderId"] == "order-1"
    assert client.calls == 2
