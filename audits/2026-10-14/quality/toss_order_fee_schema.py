"""Read-only schema contract for Toss Order/OrderExecution fee evidence.

Checks schema *availability* without retaining account details or exposing values.
Based on the public Order/OrderExecution field lists (REST OpenAPI v1.2.14
archived 2026-09-07). Later versions and actual account responses are NOT
attested by this static adapter. No client, credentials, DB, or network.
"""
from decimal import Decimal, InvalidOperation

ORDER_EXECUTION_FIELDS = frozenset((
    "filledQuantity", "averageFilledPrice", "filledAmount",
    "commission", "tax", "filledAt", "settlementDate",
))


def _finite_nonnegative(value):
    if value is None or isinstance(value, (bool, float)):
        return False
    try:
        v = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return False
    return v.is_finite() and v >= 0


def check_fee_schema(unwrapped_order):
    """Return non-sensitive status flags. Never echo broker response values."""
    fail = lambda reason: {"status": "UNVERIFIED", "reason": reason,
                           "net_pnl_eligible": False}
    if not isinstance(unwrapped_order, dict):
        return fail("NOT_AN_ORDER_OBJECT")
    if "result" in unwrapped_order:
        return fail("UNWRAP_RESPONSE_BEFORE_VALIDATION")
    execution = unwrapped_order.get("execution")
    if not isinstance(execution, dict):
        return fail("ORDER_EXECUTION_MISSING")
    currency = unwrapped_order.get("currency")
    if currency not in ("USD", "KRW"):
        return fail("TRADE_CURRENCY_UNVERIFIED")
    for field in ("filledQuantity", "averageFilledPrice", "commission", "tax"):
        if field not in execution or not _finite_nonnegative(execution[field]):
            return fail("MISSING_OR_INVALID_" + field.upper())
    if Decimal(str(execution["filledQuantity"])) <= 0 or Decimal(str(execution["averageFilledPrice"])) <= 0:
        return fail("NO_POSITIVE_FILL")
    # The archived public OrderExecution schema has no feeCurrency field,
    # and the local position_manager.py parser stores only order.currency.
    # Do not infer fee denomination merely because order.currency exists.
    return {
        "status": "FEE_AMOUNT_FIELDS_PRESENT_CURRENCY_UNVERIFIED",
        "documented_trade_currency": True,
        "commission_reported": True,
        "tax_reported": True,
        "explicit_zero_fee_supported": True,
        "fee_currency_source": "NOT_DOCUMENTED_IN_ORDER_EXECUTION",
        "net_pnl_eligible": False,
    }
