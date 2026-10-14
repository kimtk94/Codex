"""Conservative historical fill evidence from persisted broker-order telemetry.

Pure: does not access broker API, disk, secrets, or databases.
An accepted historical fill is NOT evidence of a currently empty broker order book.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _positive_decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def historical_broker_fill(order: dict, telemetry: dict | None) -> dict | None:
    if not isinstance(order, dict) or not isinstance(telemetry, dict):
        return None
    broker = telemetry.get("broker_order")
    if not isinstance(broker, dict):
        return None
    order_id = str(order.get("toss_order_id") or "")
    reported_id = str(broker.get("order_id") or "")
    if not order_id or order_id != reported_id:
        return None
    if str(broker.get("status") or "").upper() != "FILLED":
        return None
    response = broker.get("response_meta")
    if not isinstance(response, dict) or str(response.get("status_code")) != "200":
        return None
    quantity = _positive_decimal(broker.get("filled_quantity"))
    if quantity is None:
        return None
    price = _positive_decimal(broker.get("average_filled_price"))
    fill_time = broker.get("filled_at")
    if not isinstance(fill_time, str):
        return None
    try:
        stamp = datetime.fromisoformat(fill_time.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if stamp.utcoffset() is None:
        return None
    return {"filled_quantity": quantity, "average_filled_price": price,
            "filled_at": stamp.isoformat()}
