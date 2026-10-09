from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.config import Settings
from engine.r5_conditional_live import (
    _conditional_client_order_id,
    _conditional_execution_contract,
    _target_entries_for_leg,
)


def test_target_entries_10k_becomes_two_5k_chunks():
    assert _target_entries_for_leg(10000, 5000, 3) == 2


def test_target_entries_20k_is_capped_at_three_5k_chunks():
    assert _target_entries_for_leg(20000, 5000, 3) == 3


def test_target_entries_never_exceeds_max_entries():
    assert _target_entries_for_leg(50000, 5000, 3) == 3


def test_add_on_client_order_ids_are_distinct_and_stable():
    as_of = datetime(2026, 10, 6, 1, 30, tzinfo=timezone.utc)
    initial = _conditional_client_order_id("run-1", "AAA", as_of, 1)
    second = _conditional_client_order_id("run-1", "AAA", as_of, 2)
    third = _conditional_client_order_id("run-1", "AAA", as_of, 3)

    assert initial != second
    assert second != third
    assert second == _conditional_client_order_id("run-1", "AAA", as_of, 2)


def test_chunked_conditional_contract_is_5k_x3_with_15k_symbol_cap():
    settings = Settings(max_single_order_krw=5000)
    with patch.dict(
        "os.environ",
        {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_5000",
            "AUTO_TRADE_ORDER_KRW": "5000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "15000",
        },
        clear=False,
    ):
        contract = _conditional_execution_contract(settings, total_krw=20000)

    assert contract["chunked"] is True
    assert contract["order_krw"] == 5000
    assert contract["max_entries"] == 3
    assert contract["add_on_gap_buckets"] == 1
    assert contract["max_symbol_notional_krw"] == 15000


def test_chunked_conditional_rejects_single_order_limit_above_5k():
    settings = Settings(max_single_order_krw=20000)
    with patch.dict(
        "os.environ",
        {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_5000",
            "AUTO_TRADE_ORDER_KRW": "5000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "15000",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="MAX_SINGLE_ORDER_KRW=5000"):
            _conditional_execution_contract(settings, total_krw=20000)

def test_30k_conditional_contract_is_10k_x3_with_30k_caps():
    settings = Settings(
        max_single_order_krw=10000,
        live_micro_total_limit_krw=30000,
    )
    with patch.dict(
        "os.environ",
        {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_10000_30000",
            "AUTO_TRADE_ORDER_KRW": "10000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "30000",
        },
        clear=False,
    ):
        contract = _conditional_execution_contract(settings, total_krw=30000)

    assert contract["chunked"] is True
    assert contract["order_krw"] == 10000
    assert contract["max_entries"] == 3
    assert contract["max_symbol_notional_krw"] == 30000


def test_30k_conditional_contract_requires_daily_30k_cap():
    settings = Settings(
        max_single_order_krw=10000,
        live_micro_total_limit_krw=0,
    )
    with patch.dict(
        "os.environ",
        {
            "AUTO_TRADE_CONDITIONAL_CONFIRM": "CONFIRM_R5_LIVE_CONDITIONAL_10000_30000",
            "AUTO_TRADE_ORDER_KRW": "10000",
            "AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL": "3",
            "AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP": "1",
            "AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW": "30000",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="active exposure cap KRW 30000"):
            _conditional_execution_contract(settings, total_krw=30000)
