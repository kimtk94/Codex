"""Offline-only, fail-closed round-trip cash-flow arithmetic.

Only use with a COMPLETE independent per-position event inventory.
No broker requests, local state writes, inference from symbol/time, or FX assumptions.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

TRUSTED_LINKS = {"ENTRY_CLIENT_ORDER_ID", "EXIT_CLIENT_ORDER_ID",
                 "EXPLICIT_ORDER_POSITION_ID"}


def dec(value, positive=False):
    if value is None or isinstance(value, (bool, float)):
        return None  # decimal strings avoid implicit binary-float precision
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not x.is_finite() or x < 0 or (positive and x == 0):
        return None
    return x


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        x = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return x.astimezone(timezone.utc) if x.utcoffset() is not None else None
    except (ValueError, OverflowError, TypeError):
        return None


def reconstruct(position, fills, *, inventory_complete=False,
                expected_broker_order_ids=None,
                qty_tolerance="0.00000001", price_tolerance="0.02"):
    """Calculate native-currency net return or return UNVERIFIED.

    Each fill is a final, unique broker-order aggregate (not a partial update).
    Inventory completeness and association must be independently attested.\n    expected_broker_order_ids MUST originate from an independent complete\n    inventory, not be inferred from the same fills being evaluated.
    Historical broker evidence alone does not verify current account balances.
    """
    def block(reason):
        return {"status": "UNVERIFIED", "reason": reason}

    if inventory_complete is not True:
        return block("INCOMPLETE_EVENT_INVENTORY")
    if not isinstance(position, dict) or not isinstance(fills, list) or not fills:
        return block("INVALID_INPUT")
    if not isinstance(expected_broker_order_ids, (list, tuple)):
        return block("INDEPENDENT_ORDER_MANIFEST_MISSING")
    if (not expected_broker_order_ids
        or any(not isinstance(x, str) or not x for x in expected_broker_order_ids)
        or len(expected_broker_order_ids) != len(set(expected_broker_order_ids))):
        return block("INVALID_ORDER_MANIFEST")
    pid, symbol, ccy = position.get("position_id"), position.get("symbol"), position.get("currency")
    if not all(isinstance(x, str) and x.strip() for x in (pid, symbol, ccy)):
        return block("POSITION_ID_SYMBOL_CURRENCY_MISSING")
    if ccy not in ("USD", "KRW") or position.get("state") != "CLOSED":
        return block("UNSUPPORTED_CURRENCY_OR_POSITION_STATE")
    eq, xq = dec(position.get("entry_filled_quantity"), True), dec(position.get("exit_filled_quantity"), True)
    ea, xa = dec(position.get("entry_average_price"), True), dec(position.get("exit_average_price"), True)
    remain = dec(position.get("remaining_quantity"))
    qtol, ptol = dec(qty_tolerance), dec(price_tolerance)
    if any(x is None for x in (eq, xq, ea, xa, remain, qtol, ptol)):
        return block("INVALID_POSITION_OR_TOLERANCE")
    if remain > qtol or abs(eq-xq) > qtol:
        return block("POSITION_NOT_FULLY_CLOSED")

    records, seen = [], set()
    for row in fills:
        if not isinstance(row, dict):
            return block("INVALID_EVENT")
        if row.get("position_id") != pid or row.get("symbol") != symbol:
            return block("UNMATCHED_POSITION")
        if row.get("link_basis") not in TRUSTED_LINKS:
            return block("UNVERIFIED_POSITION_LINK")
        order_id = row.get("broker_order_id")
        if not isinstance(order_id, str) or not order_id or order_id in seen:
            return block("DUPLICATE_OR_MISSING_BROKER_ORDER_ID")
        seen.add(order_id)
        if row.get("reported_broker_order_id") != order_id or row.get("broker_status") != "FILLED":
            return block("UNCONFIRMED_BROKER_FILL")
        if str(row.get("http_status")) != "200":
            return block("UNCONFIRMED_HTTP_RESPONSE")
        when = stamp(row.get("filled_at"))
        if when is None:
            return block("INVALID_FILL_TIMESTAMP")
        if row.get("currency") != ccy or row.get("fee_currency") != ccy:
            return block("UNVERIFIED_FEE_CURRENCY")
        side = row.get("side")
        if side not in ("BUY", "SELL"):
            return block("INVALID_SIDE")
        quantity = dec(row.get("quantity"), True)
        price = dec(row.get("price"), True)
        commission = dec(row.get("commission"))
        tax = dec(row.get("tax"))
        if any(x is None for x in (quantity, price, commission, tax)):
            return block("MISSING_OR_INVALID_FILL_OR_FEES")
        records.append((when, side, quantity, price, commission+tax))
    if seen != set(expected_broker_order_ids):
        return block("ORDER_MANIFEST_MISMATCH")
    records.sort(key=lambda x: x[0])
    inventory, qty, notionals, fees, counts = Decimal(0), {}, {}, {}, {}
    for side in ("BUY", "SELL"):
        qty[side], notionals[side], fees[side], counts[side] = Decimal(0), Decimal(0), Decimal(0), 0
    for _, side, quantity, price, cost in records:
        inventory += quantity if side == "BUY" else -quantity
        if inventory < -qtol:
            return block("SELL_EXCEEDS_AVAILABLE_SHARES")
        qty[side] += quantity
        notionals[side] += quantity*price
        fees[side] += cost
        counts[side] += 1
    if not counts["BUY"] or not counts["SELL"]:
        return block("MISSING_ENTRY_OR_EXIT")
    if abs(qty["BUY"]-eq) > qtol or abs(qty["SELL"]-xq) > qtol or abs(inventory) > qtol:
        return block("AGGREGATE_QUANTITY_MISMATCH")
    if abs(notionals["BUY"]/qty["BUY"]-ea) > ptol or abs(notionals["SELL"]/qty["SELL"]-xa) > ptol:
        return block("WEIGHTED_PRICE_MISMATCH")
    entry_cost = notionals["BUY"] + fees["BUY"]
    net = notionals["SELL"] - fees["SELL"] - entry_cost
    if entry_cost <= 0:
        return block("NONPOSITIVE_COST_BASIS")
    return {
        "status": "RECONSTRUCTED_HISTORICAL_CASHFLOW",
        "currency": ccy, "buy_orders": counts["BUY"], "sell_orders": counts["SELL"],
        "buy_quantity": str(qty["BUY"]), "sell_quantity": str(qty["SELL"]),
        "buy_notional": str(notionals["BUY"]), "sell_notional": str(notionals["SELL"]),
        "buy_fees": str(fees["BUY"]), "sell_fees": str(fees["SELL"]),
        "gross_pnl": str(notionals["SELL"]-notionals["BUY"]),
        "net_pnl": str(net), "net_return": str(net/entry_cost),
        "net_return_pct": str(net/entry_cost*100),
        "current_broker_balance_verified": False,
    }
