"""Offline-only broker-versus-mirror reconciliation. No network, credentials, or filesystem writes."""
from decimal import Decimal, InvalidOperation

def number(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return None

def reconcile(mirror, broker, tolerance="0.000001"):
    """Require supplied snapshots; do not infer any live order state from historical events."""
    if broker is None:
        return {"status":"UNKNOWN","reason":"BROKER_SNAPSHOT_MISSING"}
    expected = {str(p["symbol"]).upper():number(p.get("remaining_quantity")) for p in mirror if p.get("state")=="OPEN"}
    actual = {str(p["symbol"]).upper():number(p.get("quantity")) for p in broker.get("holdings",[])}
    tol=number(tolerance)
    issues=[]
    for symbol in sorted(set(expected)|set(actual)):
        left,right=expected.get(symbol,Decimal(0)),actual.get(symbol,Decimal(0))
        if left is None or right is None or abs(left-right)>tol:
            issues.append({"symbol":symbol,"mirror":str(left),"broker":str(right)})
    open_orders=broker.get("open_orders")
    if open_orders is None:
        return {"status":"UNKNOWN","reason":"BROKER_OPEN_ORDERS_MISSING","holding_differences":issues}
    return {"status":"PASS" if not issues else "MISMATCH","holding_differences":issues,
            "broker_open_order_count":len(open_orders)}

