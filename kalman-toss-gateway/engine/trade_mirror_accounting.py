"""Read-only reconciliation helpers for the Kalman managed-position mirror.

Broker fill telemetry is authoritative for order-level quantities and prices.
Never infer a full position's cost basis from its first BUY order.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def dec(value):
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def json_obj(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def broker_fill(order):
    telemetry = json_obj(order.get("telemetry_json"))
    broker = telemetry.get("broker_order") or {}
    if not isinstance(broker, dict):
        broker = {}
    qty = dec(broker.get("filled_quantity"))
    price = dec(broker.get("average_filled_price"))
    status = str(broker.get("status") or "").upper()
    if status != "FILLED" or qty is None or qty <= 0 or price is None or price <= 0:
        return None
    commission, tax = dec(broker.get("commission")), dec(broker.get("tax"))
    if commission is None or tax is None:
        return None
    return {
        "quantity": qty,
        "price": price,
        "commission": commission,
        "tax": tax,
        "currency": broker.get("currency"),
    }


def broker_reconciled_status(order):
    """Upgrade stale submission rows on broker fill proof, independent of fee data."""
    broker = json_obj(order.get("telemetry_json")).get("broker_order") or {}
    if isinstance(broker, dict):
        qty, price = dec(broker.get("filled_quantity")), dec(broker.get("average_filled_price"))
        if (str(broker.get("status") or "").upper() == "FILLED"
            and qty is not None and qty > 0 and price is not None and price > 0):
            return "FILLED", "broker_fill_telemetry"
    return str(order.get("status") or "").upper(), "order_guard"


def link_position_orders(positions, orders):
    """Link add-ons only if symbol, strategy, and nonoverlapping time window agree."""
    linked = {}
    for pos in positions:
        for col, side in (("entry_client_order_id", "ENTRY"), ("exit_client_order_id", "EXIT"),
                          ("add_on_client_order_id", "ADD_ON")):
            cid = pos.get(col)
            if cid:
                linked[cid] = (pos, side)
    for order in orders:
        cid = order.get("client_order_id")
        if not cid or cid in linked or str(order.get("side") or "").upper() != "BUY":
            continue
        telemetry = json_obj(order.get("telemetry_json"))
        context = telemetry.get("signal_context") or {}
        if not isinstance(context, dict) or str(context.get("entry_type") or "").upper() != "ADD_ON":
            continue
        order_time = stamp(order.get("created_at"))
        if order_time is None:
            continue
        matches = []
        for pos in positions:
            begin, end = stamp(pos.get("created_at")), stamp(pos.get("updated_at"))
            if (begin and end and begin <= order_time <= end
                and str(pos.get("symbol") or "").upper() == str(order.get("symbol") or "").upper()
                and str(pos.get("strategy_version") or "") == str(context.get("strategy_version") or "")):
                matches.append(pos)
        if len(matches) == 1:
            linked[cid] = (matches[0], "ADD_ON")
    return linked


def position_round_trip(position, matched_orders):
    """Compute completed round trip from all linked fills or mark it non-reportable."""
    result = {"audit_status": "INCOMPLETE", "accounting_source": "BROKER_ORDER_FILLS_V2"}
    if str(position.get("state") or "").upper() != "CLOSED":
        result["audit_status"] = "POSITION_NOT_CLOSED"
        return result
    entry_orders = [o for o, leg in matched_orders if leg in ("ENTRY", "ADD_ON")]
    exit_orders = [o for o, leg in matched_orders if leg == "EXIT"]
    expected_entries = int(position.get("entry_count") or 1)
    if len(entry_orders) != expected_entries or len(exit_orders) != 1:
        result.update(reason="ENTRY_OR_EXIT_ORDER_COUNT_MISMATCH",
                      expected_entry_orders=expected_entries, observed_entry_orders=len(entry_orders),
                      observed_exit_orders=len(exit_orders))
        return result
    entry_fills = [broker_fill(o) for o in entry_orders]
    exit_fill = broker_fill(exit_orders[0])
    if any(f is None for f in entry_fills) or exit_fill is None:
        result["reason"] = "BROKER_FILL_OR_COST_MISSING"
        return result
    reported_entry_qty = dec(position.get("entry_filled_quantity"))
    reported_exit_qty = dec(position.get("entry_filled_quantity"))
    remaining = dec(position.get("remaining_quantity"))
    qty_buy = sum((f["quantity"] for f in entry_fills), Decimal(0))
    qty_sell = exit_fill["quantity"]
    tolerance = Decimal("0.000001")
    if (reported_entry_qty is None or reported_exit_qty is None or remaining is None
        or abs(qty_buy - reported_entry_qty) > tolerance or remaining != 0
        or abs(qty_sell - (reported_entry_qty - remaining)) > tolerance):
        result.update(reason="FILL_QUANTITY_MISMATCH", entry_qty=str(qty_buy),
                      exit_qty=str(qty_sell), position_entry_qty=str(reported_entry_qty),
                      position_remaining_qty=str(remaining))
        return result
    currencies = {f["currency"] for f in entry_fills + [exit_fill] if f.get("currency")}
    if len(currencies) > 1:
        result["reason"] = "CURRENCY_MISMATCH"
        return result
    buy_amount = sum((f["quantity"] * f["price"] for f in entry_fills), Decimal(0))
    sell_amount = exit_fill["quantity"] * exit_fill["price"]
    entry_fees = sum((f["commission"] + f["tax"] for f in entry_fills), Decimal(0))
    exit_fees = exit_fill["commission"] + exit_fill["tax"]
    if buy_amount <= 0 or buy_amount + entry_fees <= 0:
        result["reason"] = "INVALID_COST_BASIS"
        return result
    gross = sell_amount / buy_amount - 1
    net = (sell_amount - exit_fees) / (buy_amount + entry_fees) - 1
    reported_basis = dec(position.get("entry_avg_fill_price"))
    basis_difference_bps = None
    if reported_basis and reported_basis > 0:
        basis_difference_bps = (reported_basis - buy_amount / qty_buy) / (buy_amount / qty_buy) * 10000
    result.update({
        "audit_status": "PASS",
        "entry_leg_count": len(entry_fills),
        "entry_filled_quantity": str(qty_buy),
        "exit_filled_quantity": str(qty_sell),
        "entry_notional_native": float(buy_amount),
        "exit_notional_native": float(sell_amount),
        "entry_fees_native": float(entry_fees),
        "exit_fees_native": float(exit_fees),
        "position_cost_basis_difference_bps": float(basis_difference_bps) if basis_difference_bps is not None else None,
        "gross_return": float(gross),
        "net_return": float(net),
        "gross_return_pct": float(gross * 100),
        "net_return_pct": float(net * 100),
        "total_cost_native": float(entry_fees + exit_fees),
        "round_trip_cost_bps": float((entry_fees + exit_fees) / buy_amount * 10000),
    })
    return result
