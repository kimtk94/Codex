from __future__ import annotations

import os
from decimal import Decimal

from app.config import Settings
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient
from engine.auto_trade import (
    _has_open_buy_order,
    _holding_items,
    _nonzero_holdings,
    _open_order_items,
    _symbol_position_quantity,
    _usd_order_size,
    load_signal,
)


def _enabled(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


async def evaluate_live_readiness(settings: Settings) -> dict:
    """Read-only evaluation of the same entry gates used by engine.auto_trade.

    This function never reserves a position and never submits an order.
    """
    enabled = _enabled("AUTO_TRADE_ENABLED")
    mode = os.environ.get("AUTO_TRADE_EXECUTION_MODE", "DRY_RUN").strip().upper()
    policy = os.environ.get("AUTO_TRADE_SIGNAL_POLICY", "APPROVED_ONLY").strip().upper()
    strategy_version = os.environ.get("AUTO_TRADE_STRATEGY_VERSION", "").strip() or None
    require_flat = _enabled("AUTO_TRADE_REQUIRE_ACCOUNT_FLAT", "true")
    shadow_confirmed = (
        policy != "SHADOW_CANARY"
        or os.environ.get("AUTO_TRADE_SHADOW_CONFIRM", "") == "CONFIRM_SHADOW_CANARY"
    )

    signal = None
    signal_error = None
    if strategy_version and policy in {"APPROVED_ONLY", "SHADOW_CANARY"}:
        try:
            signal = load_signal("LIVE", strategy_version, policy)
        except Exception as exc:  # fail closed, but preserve diagnostics
            signal_error = f"{type(exc).__name__}: {exc}"

    store = ManagedPositionStore(settings.state_db_path)
    active_positions = store.active()

    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    holdings_items = _holding_items(await client.holdings())
    open_order_items = _open_order_items(await client.orders("OPEN"))
    nonzero_holdings = _nonzero_holdings(holdings_items)
    account_flat = len(nonzero_holdings) == 0 and len(open_order_items) == 0

    symbol = str((signal or {}).get("symbol") or "").upper()
    position_qty = _symbol_position_quantity(holdings_items, symbol) if symbol else Decimal("0")
    open_buy = _has_open_buy_order(open_order_items, symbol) if symbol else False

    buying = unwrap(await client.buying_power("USD")) or {}
    cash_power = Decimal(str(buying.get("cashBuyingPower") or "0"))
    sizing_mode = os.environ.get("AUTO_TRADE_SIZING_MODE", "FIXED_USD").strip().upper()
    usd_krw_rate = None
    if sizing_mode == "FIXED_KRW":
        fx_payload = unwrap(await client.exchange_rate("USD", "KRW")) or {}
        usd_krw_rate = Decimal(str(fx_payload.get("rate") or "0"))

    order_usd, sizing = _usd_order_size(cash_power, usd_krw_rate=usd_krw_rate)

    checks = {
        "auto_trade_enabled": enabled,
        "execution_mode_live": mode == "LIVE",
        "strategy_locked": bool(strategy_version),
        "signal_policy_valid": policy in {"APPROVED_ONLY", "SHADOW_CANARY"},
        "shadow_confirmed": shadow_confirmed,
        "live_gate_open": settings.live_gate_open,
        "eligible_signal_found": signal is not None,
        "managed_position_clear": len(active_positions) == 0,
        "order_window_open": bool(window_open),
        "account_flat": (account_flat if require_flat else True),
        "symbol_position_clear": position_qty <= 0,
        "open_buy_clear": not open_buy,
        "cash_sufficient": order_usd is not None,
    }

    reason_map = [
        ("auto_trade_enabled", "AUTO_TRADE_DISABLED"),
        ("execution_mode_live", "EXECUTION_MODE_NOT_LIVE"),
        ("strategy_locked", "STRATEGY_VERSION_NOT_LOCKED"),
        ("signal_policy_valid", "SIGNAL_POLICY_INVALID"),
        ("shadow_confirmed", "SHADOW_CANARY_CONFIRMATION_MISSING"),
        ("live_gate_open", "LIVE_GATE_CLOSED"),
        ("eligible_signal_found", "NO_ELIGIBLE_SIGNAL"),
        ("managed_position_clear", "MANAGED_POSITION_ACTIVE"),
        ("order_window_open", "US_ORDER_WINDOW_CLOSED"),
        ("account_flat", "ACCOUNT_NOT_FLAT"),
        ("symbol_position_clear", "BROKER_POSITION_NOT_FLAT"),
        ("open_buy_clear", "OPEN_BUY_ORDER_EXISTS"),
        ("cash_sufficient", "INSUFFICIENT_CASH_FOR_CONFIGURED_SIZE"),
    ]
    reason_codes = [code for key, code in reason_map if not checks[key]]
    if signal_error:
        reason_codes.insert(0, "SIGNAL_QUERY_FAILED")

    return {
        "schema_version": "kalman-live-readiness-v1",
        "ready": not reason_codes,
        "reason_codes": reason_codes,
        "checks": checks,
        "execution_mode": mode,
        "signal_policy": policy,
        "strategy_version": strategy_version,
        "candidate": {
            "symbol": symbol or None,
            "as_of": (signal or {}).get("as_of"),
            "run_id": (signal or {}).get("run_id"),
        } if signal else None,
        "require_account_flat": require_flat,
        "active_managed_positions": active_positions,
        "nonzero_holdings": nonzero_holdings,
        "open_order_count": len(open_order_items),
        "broker_holding_quantity": str(position_qty),
        "open_buy_order_exists": open_buy,
        "us_fractional_order_window_open": bool(window_open),
        "market_window": window_info,
        "cash_buying_power_usd": str(cash_power),
        "selected_order_usd": str(order_usd) if order_usd is not None else None,
        "sizing": sizing,
        "signal_error": signal_error,
        "execution_attempted": False,
    }
