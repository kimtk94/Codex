"""Pure policy helpers for the guarded OPEN_CARRY 5K x 2 strategy."""
from __future__ import annotations

from decimal import Decimal

STRATEGY = "R5.1_BASE_HGB"
TARGET_KRW = 10_000
CHUNK_KRW = 5_000
MAX_ENTRIES = 2


def evaluate_leg1(
    score: float | None,
    confidence_threshold: float,
    open_price: Decimal,
    price_5m: Decimal,
) -> tuple[bool, float | None, str]:
    if score is None:
        return False, None, "MISSING_SCORE"
    if open_price <= 0 or price_5m <= 0:
        return False, None, "INVALID_PRICE"
    momentum = float(price_5m / open_price - Decimal("1"))
    if score <= confidence_threshold:
        return False, momentum, "SCORE_AT_OR_BELOW_CONFIDENCE"
    if momentum <= 0:
        return False, momentum, "FIRST_5M_NOT_POSITIVE"
    return True, momentum, "PASS"


def evaluate_leg2(
    leg1_eligible: bool,
    price_5m: Decimal,
    price_later: Decimal,
) -> tuple[bool, float | None, str]:
    if not leg1_eligible:
        return False, None, "LEG1_NOT_ELIGIBLE"
    if price_5m <= 0 or price_later <= 0:
        return False, None, "INVALID_PRICE"
    continuation = float(price_later / price_5m - Decimal("1"))
    if continuation < 0:
        return False, continuation, "SECOND_5M_WEAKENED"
    return True, continuation, "PASS"


def validate_execution_contract(
    *,
    order_krw: int,
    total_krw: int,
    max_entries: int,
    max_single_order_krw: int,
) -> tuple[bool, str]:
    if int(order_krw) != CHUNK_KRW:
        return False, "OPEN_CARRY_ORDER_MUST_BE_5000"
    if int(total_krw) != TARGET_KRW:
        return False, "OPEN_CARRY_TOTAL_MUST_BE_10000"
    if int(max_entries) != MAX_ENTRIES:
        return False, "OPEN_CARRY_MAX_ENTRIES_MUST_BE_2"
    if int(max_single_order_krw) != CHUNK_KRW:
        return False, "MAX_SINGLE_ORDER_KRW_MUST_BE_5000"
    return True, "PASS"
