"""Validate externally supplied, sanitized broker snapshots; never access credentials or network."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

def ts(value):
    try:
        x=datetime.fromisoformat(value.replace("Z","+00:00"))
        return x if x.tzinfo else None
    except (AttributeError, ValueError):
        return None

def validate(payload):
    issues=[]
    if not isinstance(payload,dict):
        return ["NOT_OBJECT"]
    stamp=ts(payload.get("captured_at"))
    if stamp is None:
        issues.append("INVALID_CAPTURE_TIME")
    for key in ("holdings","open_orders"):
        if not isinstance(payload.get(key),list):
            issues.append(f"{key.upper()}_NOT_LIST")
    for p in payload.get("holdings",[]) if isinstance(payload.get("holdings"),list) else []:
        symbol=p.get("symbol") if isinstance(p,dict) else None
        try: q=Decimal(str(p["quantity"]))
        except (KeyError,TypeError,InvalidOperation,ValueError): q=None
        if not isinstance(symbol,str) or not symbol or q is None or q<0:
            issues.append("INVALID_HOLDING")
    orders=payload.get("open_orders",[])
    if isinstance(orders,list):
        for o in orders:
            if not isinstance(o,dict) or not o.get("symbol") or not o.get("side"):
                issues.append("INVALID_OPEN_ORDER")
    return sorted(set(issues))
