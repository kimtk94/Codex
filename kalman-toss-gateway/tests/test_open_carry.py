from decimal import Decimal

from engine.open_carry_policy import (
    evaluate_leg1,
    evaluate_leg2,
    validate_execution_contract,
)


def test_leg1_requires_score_strictly_above_threshold():
    ok, momentum, reason = evaluate_leg1(0.5, 0.5, Decimal("100"), Decimal("101"))
    assert ok is False
    assert momentum == 0.01
    assert reason == "SCORE_AT_OR_BELOW_CONFIDENCE"


def test_leg1_requires_positive_first_five_minute_momentum():
    ok, momentum, reason = evaluate_leg1(0.6, 0.5, Decimal("100"), Decimal("100"))
    assert ok is False
    assert momentum == 0.0
    assert reason == "FIRST_5M_NOT_POSITIVE"


def test_leg1_passes_on_confident_positive_open():
    ok, momentum, reason = evaluate_leg1(0.6, 0.5, Decimal("100"), Decimal("101"))
    assert ok is True
    assert momentum == 0.01
    assert reason == "PASS"


def test_leg2_rejects_weakening_after_leg1():
    ok, continuation, reason = evaluate_leg2(True, Decimal("101"), Decimal("100.99"))
    assert ok is False
    assert continuation < 0
    assert reason == "SECOND_5M_WEAKENED"


def test_leg2_allows_flat_or_stronger_price():
    flat = evaluate_leg2(True, Decimal("101"), Decimal("101"))
    stronger = evaluate_leg2(True, Decimal("101"), Decimal("102"))
    assert flat == (True, 0.0, "PASS")
    assert stronger[0] is True
    assert stronger[1] > 0
    assert stronger[2] == "PASS"


def test_execution_contract_accepts_exact_5000x2():
    assert validate_execution_contract(
        order_krw=5000,
        total_krw=10000,
        max_entries=2,
        max_single_order_krw=5000,
    ) == (True, "PASS")


def test_execution_contract_rejects_single_10000_order():
    ok, reason = validate_execution_contract(
        order_krw=10000,
        total_krw=10000,
        max_entries=2,
        max_single_order_krw=5000,
    )
    assert ok is False
    assert reason == "OPEN_CARRY_ORDER_MUST_BE_5000"


def test_execution_contract_rejects_exposure_above_10000():
    ok, reason = validate_execution_contract(
        order_krw=5000,
        total_krw=15000,
        max_entries=2,
        max_single_order_krw=5000,
    )
    assert ok is False
    assert reason == "OPEN_CARRY_TOTAL_MUST_BE_10000"


def test_execution_contract_requires_two_entry_cap():
    ok, reason = validate_execution_contract(
        order_krw=5000,
        total_krw=10000,
        max_entries=3,
        max_single_order_krw=5000,
    )
    assert ok is False
    assert reason == "OPEN_CARRY_MAX_ENTRIES_MUST_BE_2"
