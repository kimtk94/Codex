"""Offline broker/mirror reconciliation. No network, filesystem, or credentials."""
from decimal import Decimal, InvalidOperation
from broker_snapshot_contract import validate

def number(x):
    try:
        v=Decimal(str(x))
        return v if v.is_finite() and v>=0 else None
    except (InvalidOperation,TypeError,ValueError):
        return None

def reconcile(mirror, broker, tolerance="0.000001", *, expected_submitted=None):
    if broker is None:
        return {"status":"UNKNOWN","reason":"BROKER_SNAPSHOT_MISSING"}
    errors=validate(broker)
    if errors:
        return {"status":"UNKNOWN","reason":"INVALID_BROKER_SNAPSHOT","errors":errors}
    tol=number(tolerance)
    if tol is None:
        return {"status":"UNKNOWN","reason":"INVALID_TOLERANCE"}
    expected={}
    for p in mirror:
        if p.get("state")!="OPEN":
            continue
        sym=str(p.get("symbol","")).strip().upper()
        qty=number(p.get("remaining_quantity"))
        if not sym or qty is None or sym in expected:
            return {"status":"UNKNOWN","reason":"INVALID_OR_DUPLICATE_MIRROR_POSITION"}
        expected[sym]=qty
    actual={}
    for p in broker["holdings"]:
        sym=p["symbol"].strip().upper()
        qty=number(p["quantity"])
        if qty is None or sym in actual:
            return {"status":"UNKNOWN","reason":"INVALID_OR_DUPLICATE_BROKER_HOLDING"}
        actual[sym]=qty
    differences=[]
    for sym in sorted(set(expected)|set(actual)):
        a,b=expected.get(sym,Decimal(0)),actual.get(sym,Decimal(0))
        if abs(a-b)>tol:
            differences.append({"symbol":sym,"mirror":str(a),"broker":str(b)})
    if differences:
        return {"status":"MISMATCH","holding_differences":differences,
                "broker_open_order_count":len(broker["open_orders"])}
    if expected_submitted is not None and expected_submitted>0:
        return {"status":"PARTIAL","reason":"SUBMITTED_ORDER_LIFECYCLE_UNVERIFIED",
                "holding_differences":[],"broker_open_order_count":len(broker["open_orders"])}
    return {"status":"HOLDINGS_MATCH","holding_differences":[],
            "broker_open_order_count":len(broker["open_orders"])}
