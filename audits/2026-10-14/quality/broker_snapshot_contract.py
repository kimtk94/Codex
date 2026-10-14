"""Validate externally supplied, sanitized broker snapshots.

Pure/side-effect-free: no credentials, filesystem, network, or logs.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math


def ts(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _utc_now(now):
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, str):
        return ts(now)
    if isinstance(now, datetime) and now.utcoffset() is not None:
        return now.astimezone(timezone.utc)
    return None


def validate(payload, *, now=None, max_age_seconds=300, max_future_skew_seconds=30):
    """A snapshot must be complete, finite-valued, and fresh.

    Time thresholds are inclusive. The caller may pass a pinned UTC evaluation
    time for historical replay; live callers should omit now.
    """
    if not isinstance(payload, dict):
        return ["NOT_OBJECT"]
    issues = []
    current = _utc_now(now)
    if current is None:
        issues.append("INVALID_EVALUATION_TIME")
    try:
        max_age = float(max_age_seconds)
        future_skew = float(max_future_skew_seconds)
        if not (math.isfinite(max_age) and max_age > 0 and
                math.isfinite(future_skew) and future_skew >= 0):
            raise ValueError("invalid time bounds")
    except (TypeError, ValueError, OverflowError):
        issues.append("INVALID_TIME_BOUNDS")
        max_age, future_skew = None, None

    stamp = ts(payload.get("captured_at"))
    if stamp is None:
        issues.append("INVALID_CAPTURE_TIME")
    elif current is not None and max_age is not None:
        age = (current - stamp).total_seconds()
        if age > max_age:
            issues.append("STALE_BROKER_SNAPSHOT")
        elif age < -future_skew:
            issues.append("FUTURE_BROKER_SNAPSHOT")

    for key in ("holdings", "open_orders"):
        if not isinstance(payload.get(key), list):
            issues.append(f"{key.upper()}_NOT_LIST")

    holdings = payload.get("holdings")
    if isinstance(holdings, list):
        for row in holdings:
            if not isinstance(row, dict):
                issues.append("INVALID_HOLDING")
                continue
            symbol = row.get("symbol")
            try:
                qty = Decimal(str(row["quantity"]))
            except (KeyError, TypeError, InvalidOperation, ValueError):
                qty = None
            if (not isinstance(symbol, str) or not symbol.strip() or
                    qty is None or not qty.is_finite() or qty < 0):
                issues.append("INVALID_HOLDING")

    orders = payload.get("open_orders")
    if isinstance(orders, list):
        for row in orders:
            if (not isinstance(row, dict) or
                    not isinstance(row.get("symbol"), str) or
                    not row["symbol"].strip() or
                    str(row.get("side", "")).upper() not in {"BUY", "SELL"}):
                issues.append("INVALID_OPEN_ORDER")
    return sorted(set(issues))
