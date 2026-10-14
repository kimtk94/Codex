"""Fail-closed explicit link from a local BUY order to a managed position.

No network, database, filesystem or broker I/O. Only newly tagged historical
orders can be linked; symbol/time matching is explicitly forbidden.
"""
from __future__ import annotations
import hashlib


def _expected_client_id(run_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f"{run_id}|{symbol}|BUY".encode()).hexdigest()[:12]
    clean = "".join(c for c in symbol if c.isalnum() or c in "-_")[:8]
    return f"kalman-{clean}-{digest}"[:36]


def explicit_buy_link(order: dict, telemetry: dict, positions: list[dict]) -> dict:
    """Return a locally verified provenance link, never broker confirmation."""
    def blocked(reason: str) -> dict:
        return {"status": "UNKNOWN", "reason": reason}

    if not isinstance(order, dict) or not isinstance(telemetry, dict) or not isinstance(positions, list):
        return blocked("INVALID_INPUT")
    ctx = telemetry.get("signal_context")
    if not isinstance(ctx, dict):
        return blocked("MISSING_SIGNAL_CONTEXT")
    pid = ctx.get("managed_position_id")
    if not isinstance(pid, str) or not pid.strip():
        return blocked("EXPLICIT_POSITION_ID_MISSING")
    symbol = str(order.get("symbol") or "").strip().upper()
    if not symbol or symbol != str(ctx.get("symbol") or "").strip().upper():
        return blocked("SYMBOL_MISMATCH")
    if str(order.get("side") or "").upper() != "BUY":
        return blocked("UNSUPPORTED_SIDE")
    kind = ctx.get("entry_type")
    if kind not in ("ADD_ON", "INITIAL"):
        return blocked("UNSUPPORTED_ENTRY_TYPE")
    run = ctx.get("run_id")
    if not isinstance(run, str) or not run.strip():
        return blocked("RUN_ID_MISSING")
    if order.get("client_order_id") != _expected_client_id(run, symbol):
        return blocked("CLIENT_ORDER_ID_MISMATCH")
    candidates = [p for p in positions if isinstance(p, dict) and p.get("position_id") == pid]
    if len(candidates) != 1:
        return blocked("POSITION_NOT_UNIQUE")
    pos = candidates[0]
    if str(pos.get("symbol") or "").strip().upper() != symbol:
        return blocked("POSITION_SYMBOL_MISMATCH")
    strategy = ctx.get("strategy_version")
    if not isinstance(strategy, str) or not strategy or strategy != pos.get("strategy_version"):
        return blocked("STRATEGY_VERSION_MISMATCH")
    if kind == "INITIAL":
        if run != pos.get("entry_run_id") or order.get("client_order_id") != pos.get("entry_client_order_id"):
            return blocked("INITIAL_ENTRY_MISMATCH")
    else:
        before = ctx.get("entry_count_before")
        count = pos.get("entry_count")
        if (not isinstance(before, int) or isinstance(before, bool) or before < 1
                or not isinstance(count, int) or isinstance(count, bool) or before > count):
            return blocked("INVALID_ADD_ON_ORDINAL")
    return {"status": "EXPLICIT_LOCAL_LINK", "position_id": pid, "leg": kind,
            "broker_confirmed": False}
