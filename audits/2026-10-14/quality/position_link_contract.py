"""Conservative offline attribution for explicitly tagged future orders.

Historical order attribution MUST NOT be guessed from symbol or timestamps.
A matching local ID is a source link, not broker proof or fee completeness.
"""


def classify_local_position_link(order, positions):
    if not isinstance(order, dict) or not isinstance(positions, list):
        return {"status": "UNKNOWN", "reason": "INVALID_INPUT"}
    context = order.get("signal_context")
    if not isinstance(context, dict):
        return {"status": "UNKNOWN", "reason": "SIGNAL_CONTEXT_MISSING"}
    pid = context.get("managed_position_id")
    if not isinstance(pid, str) or not pid:
        return {"status": "UNKNOWN", "reason": "EXPLICIT_POSITION_ID_MISSING"}
    side = str(order.get("side") or "").upper()
    kind = context.get("entry_type")
    if side != "BUY" or kind not in ("INITIAL", "ADD_ON"):
        return {"status": "UNKNOWN", "reason": "UNSUPPORTED_ORDER_LEG"}
    symbol = str(order.get("symbol") or "").upper()
    if not symbol or symbol != str(context.get("symbol") or "").upper():
        return {"status": "UNKNOWN", "reason": "CONTEXT_SYMBOL_MISMATCH"}
    matches = [p for p in positions if isinstance(p, dict) and p.get("position_id") == pid]
    if len(matches) != 1:
        return {"status": "UNKNOWN", "reason": "POSITION_ID_NOT_UNIQUE_OR_MISSING"}
    candidate = matches[0]
    if symbol != str(candidate.get("symbol") or "").upper():
        return {"status": "UNKNOWN", "reason": "POSITION_SYMBOL_MISMATCH"}
    if kind == "INITIAL" and context.get("run_id") != candidate.get("entry_run_id"):
        return {"status": "UNKNOWN", "reason": "INITIAL_RUN_ID_MISMATCH"}
    if kind == "ADD_ON" and (
        not isinstance(context.get("entry_count_before"), int)
        or isinstance(context.get("entry_count_before"), bool)
        or context["entry_count_before"] < 1
    ):
        return {"status": "UNKNOWN", "reason": "INVALID_ADD_ON_ORDINAL"}
    return {"status": "EXPLICIT_LOCAL_LINK", "position_id": pid,
            "leg": kind, "broker_confirmed": False}
