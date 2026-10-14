"""Offline broker/mirror reconciliation. No network, filesystem, or credentials."""
from decimal import Decimal, InvalidOperation
import math
from broker_snapshot_contract import _utc_now, ts, validate


def number(x):
    try:
        v = Decimal(str(x))
        return v if v.is_finite() and v >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def reconcile(mirror, broker, tolerance="0.000001", *,
              mirror_as_of=None, now=None, max_age_seconds=300,
              max_skew_seconds=300, expected_submitted=None):
    """Compare timestamp-matched *sanitized* holdings.

    Never equate a holdings match with a successful order-lifecycle audit.
    Live use omits now (uses UTC clock); historical replay may pin now.
    mirror_as_of is an independently observed mirror snapshot timestamp.
    """
    if broker is None:
        return {"status": "UNKNOWN", "reason": "BROKER_SNAPSHOT_MISSING"}
    current = _utc_now(now)
    if current is None:
        return {"status": "UNKNOWN", "reason": "INVALID_EVALUATION_TIME"}
    errors = validate(broker, now=current, max_age_seconds=max_age_seconds)
    if errors:
        return {"status": "UNKNOWN", "reason": "INVALID_BROKER_SNAPSHOT",
                "errors": errors}
    mirror_stamp = ts(mirror_as_of)
    if mirror_stamp is None:
        return {"status": "UNKNOWN", "reason": "MIRROR_TIMESTAMP_MISSING"}
    mirror_age = (current - mirror_stamp).total_seconds()
    try:
        age_limit = float(max_age_seconds)
        skew_limit = float(max_skew_seconds)
        if not (math.isfinite(age_limit) and math.isfinite(skew_limit) and
                age_limit > 0 and skew_limit >= 0):
            raise ValueError("Invalid bounds")
    except (TypeError, ValueError, OverflowError):
        return {"status": "UNKNOWN", "reason": "INVALID_TIME_BOUNDS"}
    if mirror_age > age_limit:
        return {"status": "UNKNOWN", "reason": "STALE_MIRROR_SNAPSHOT"}
    if mirror_age < -30:
        return {"status": "UNKNOWN", "reason": "FUTURE_MIRROR_SNAPSHOT"}
    skew = abs((ts(broker["captured_at"]) - mirror_stamp).total_seconds())
    if skew > skew_limit:
        return {"status": "UNKNOWN", "reason": "SNAPSHOT_TIME_SKEW"}
    tol = number(tolerance)
    if tol is None:
        return {"status": "UNKNOWN", "reason": "INVALID_TOLERANCE"}
    if not isinstance(mirror, list):
        return {"status": "UNKNOWN", "reason": "INVALID_MIRROR"}
    expected = {}
    for p in mirror:
        if not isinstance(p, dict):
            return {"status": "UNKNOWN", "reason": "INVALID_MIRROR"}
        if p.get("state") != "OPEN":
            continue
        sym = str(p.get("symbol", "")).strip().upper()
        qty = number(p.get("remaining_quantity"))
        if not sym or qty is None or sym in expected:
            return {"status": "UNKNOWN", "reason": "INVALID_OR_DUPLICATE_MIRROR_POSITION"}
        expected[sym] = qty
    actual = {}
    for p in broker["holdings"]:
        sym = p["symbol"].strip().upper()
        qty = number(p["quantity"])
        if qty is None or sym in actual:
            return {"status": "UNKNOWN", "reason": "INVALID_OR_DUPLICATE_BROKER_HOLDING"}
        actual[sym] = qty
    differences = []
    for sym in sorted(set(expected) | set(actual)):
        a, b = expected.get(sym, Decimal(0)), actual.get(sym, Decimal(0))
        if abs(a - b) > tol:
            differences.append({"symbol": sym, "mirror": str(a), "broker": str(b)})
    result = {"holding_differences": differences,
              "broker_open_order_count": len(broker["open_orders"])}
    if differences:
        return {"status": "MISMATCH", **result}
    if expected_submitted is not None:
        if (not isinstance(expected_submitted, int) or
                isinstance(expected_submitted, bool) or expected_submitted < 0):
            return {"status": "UNKNOWN", "reason": "INVALID_SUBMITTED_COUNT"}
    if expected_submitted is not None and expected_submitted > 0:
        return {"status": "PARTIAL",
                "reason": "SUBMITTED_ORDER_LIFECYCLE_UNVERIFIED", **result}
    if broker["open_orders"]:
        return {"status": "PARTIAL", "reason": "BROKER_OPEN_ORDERS_UNRECONCILED", **result}
    return {"status": "HOLDINGS_MATCH", **result}
