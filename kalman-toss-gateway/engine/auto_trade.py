"""Strict DB-to-Toss automated entry bridge.

Modes:
- DRY_RUN: read-only broker/account checks and order sizing; never submits.
- LIVE: requires a locked strategy, explicit signal policy, broker/account gates,
  local idempotency, and the global two-key live gate.

Position exits are handled separately by engine.position_manager.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import execute_order, prepare_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient

TARGET_EXIT_BUCKETS = 4


def _client_order_id(run_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f'{run_id}|{symbol}|BUY'.encode()).hexdigest()[:12]
    clean_symbol = ''.join(c for c in symbol.upper() if c.isalnum() or c in '-_')[:8]
    return f'kalman-{clean_symbol}-{digest}'[:36]


def _bool(value) -> bool:
    return str(value or '').strip().lower() == 'true'


def _signal_shape_ok(signal: dict, policy: str) -> bool:
    payload = signal.get('payload') or {}
    if str(signal.get('position_state', '')).upper() != 'FLAT':
        return False
    if policy == 'APPROVED_ONLY':
        return (
            str(signal.get('signal', '')).upper() == 'BUY'
            and signal.get('entry_allowed') is True
            and str(signal.get('risk_gate', '')).upper() == 'PASS'
            and _bool(payload.get('live_execution'))
        )
    if policy == 'SHADOW_CANARY':
        return (
            str(signal.get('signal', '')).upper() == 'SHADOW'
            and _bool(payload.get('allow_trade_shadow'))
            and _bool(payload.get('shadow_entry_this_signal'))
        )
    return False


def load_signal(mode: str, strategy_version: str | None, policy: str):
    db_url = os.environ.get('DATABASE_URL_WRITER')
    if not db_url:
        raise RuntimeError('DATABASE_URL_WRITER is missing')

    if mode == 'LIVE':
        max_age = int(os.environ.get('AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES', '90'))
    else:
        max_age = int(os.environ.get('AUTO_TRADE_DRY_RUN_MAX_SIGNAL_AGE_MINUTES', '1440'))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age)

    where = [
        "s.market='US'",
        's.as_of >= %s',
        "d.status='READY'",
        'd.stale_after > now()',
    ]
    params: list[object] = [cutoff]

    if strategy_version:
        where.append('s.strategy_version=%s')
        params.append(strategy_version)

    if mode == 'LIVE' and policy == 'APPROVED_ONLY':
        where.extend([
            "s.signal='BUY'",
            's.entry_allowed IS TRUE',
            "upper(COALESCE(s.risk_gate,''))='PASS'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'live_execution','false'))='true'",
        ])
    elif mode == 'LIVE' and policy == 'SHADOW_CANARY':
        where.extend([
            "s.signal='SHADOW'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'",
            "lower(COALESCE(s.payload->>'shadow_entry_this_signal','false'))='true'",
        ])

    sql = f"""
        SELECT s.run_id,s.symbol,s.as_of,s.strategy_version,s.signal,s.entry_allowed,
               s.risk_gate,s.position_state,s.payload,d.stale_after,d.status
        FROM strategy_signal s
        JOIN dashboard_snapshot d ON d.run_id=s.run_id AND d.market=s.market
        WHERE {' AND '.join(where)}
        ORDER BY s.as_of DESC
        LIMIT 1
    """
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def _holding_items(payload) -> list[dict]:
    data = unwrap(payload) or {}
    return list(data.get('items') or []) if isinstance(data, dict) else []


def _open_order_items(payload) -> list[dict]:
    data = unwrap(payload) or {}
    if isinstance(data, dict):
        return list(data.get('orders') or data.get('items') or [])
    return list(data or [])


def _nonzero_holdings(items: list[dict]) -> list[dict]:
    out = []
    for item in items:
        try:
            qty = Decimal(str(item.get('quantity') or '0'))
        except Exception:
            qty = Decimal('0')
        if qty != 0:
            out.append({
                'symbol': str(item.get('symbol') or '').upper(),
                'marketCountry': item.get('marketCountry'),
                'currency': item.get('currency'),
                'quantity': str(qty),
            })
    return out


def _symbol_position_quantity(items: list[dict], symbol: str) -> Decimal:
    total = Decimal('0')
    for item in items:
        if str(item.get('symbol', '')).upper() == symbol.upper():
            total += Decimal(str(item.get('quantity') or '0'))
    return total


def _has_open_buy_order(items: list[dict], symbol: str) -> bool:
    return any(
        str(order.get('symbol', '')).upper() == symbol.upper()
        and str(order.get('side', '')).upper() == 'BUY'
        for order in items
    )


def _usd_order_size(cash_buying_power: Decimal) -> tuple[Decimal | None, dict]:
    mode = os.environ.get('AUTO_TRADE_SIZING_MODE', 'FIXED_USD').strip().upper()
    reserve = Decimal(os.environ.get('AUTO_TRADE_CASH_RESERVE_USD', '0'))
    minimum = Decimal(os.environ.get('AUTO_TRADE_MIN_ORDER_USD', '1'))
    maximum = Decimal(os.environ.get('AUTO_TRADE_MAX_ORDER_USD', '2'))
    spendable = max(Decimal('0'), cash_buying_power - reserve)

    if mode == 'FIXED_USD':
        raw = Decimal(os.environ.get('AUTO_TRADE_ORDER_USD', '2'))
    elif mode == 'CASH_FRACTION':
        fraction = Decimal(os.environ.get('AUTO_TRADE_CASH_FRACTION', '0.10'))
        if fraction <= 0 or fraction > 1:
            raise RuntimeError('AUTO_TRADE_CASH_FRACTION must be > 0 and <= 1')
        raw = spendable * fraction
    else:
        raise RuntimeError('AUTO_TRADE_SIZING_MODE must be FIXED_USD or CASH_FRACTION')

    if maximum > 0:
        raw = min(raw, maximum)
    amount = min(raw, spendable).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    detail = {
        'sizingMode': mode,
        'cashBuyingPowerUsd': str(cash_buying_power),
        'cashReserveUsd': str(reserve),
        'spendableCashUsd': str(spendable),
        'minOrderUsd': str(minimum),
        'maxOrderUsd': str(maximum),
        'cashFraction': os.environ.get('AUTO_TRADE_CASH_FRACTION', '0.10'),
    }
    if amount < minimum or amount <= 0:
        return None, detail
    detail['selectedOrderUsd'] = str(amount)
    return amount, detail


async def main_async() -> int:
    load_dotenv(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env'), override=True)

    if os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() != 'true':
        print('AUTO_TRADE_DISABLED')
        return 0

    mode = os.environ.get('AUTO_TRADE_EXECUTION_MODE', 'DRY_RUN').strip().upper()
    if mode not in {'DRY_RUN', 'LIVE'}:
        raise RuntimeError('AUTO_TRADE_EXECUTION_MODE must be DRY_RUN or LIVE')

    policy = os.environ.get('AUTO_TRADE_SIGNAL_POLICY', 'APPROVED_ONLY').strip().upper()
    if policy not in {'APPROVED_ONLY', 'SHADOW_CANARY'}:
        raise RuntimeError('AUTO_TRADE_SIGNAL_POLICY must be APPROVED_ONLY or SHADOW_CANARY')

    strategy_version = os.environ.get('AUTO_TRADE_STRATEGY_VERSION', '').strip() or None
    if mode == 'LIVE' and not strategy_version:
        print('LIVE_STRATEGY_VERSION_NOT_LOCKED')
        return 2
    if mode == 'LIVE' and policy == 'SHADOW_CANARY':
        if os.environ.get('AUTO_TRADE_SHADOW_CONFIRM', '') != 'CONFIRM_SHADOW_CANARY':
            print('SHADOW_CANARY_CONFIRMATION_MISSING')
            return 2

    settings = Settings()
    signal = load_signal(mode, strategy_version, policy)
    if not signal:
        print('NO_ELIGIBLE_SIGNAL')
        return 0

    symbol = signal['symbol'].upper()
    live_symbol_allowed = settings.symbol_allowed(symbol)
    if mode == 'LIVE' and not live_symbol_allowed:
        print('SIGNAL_SYMBOL_NOT_ALLOWED', symbol)
        return 0

    store = ManagedPositionStore(settings.state_db_path)
    active_positions = store.active()
    if mode == 'LIVE' and active_positions:
        print('MANAGED_POSITION_ACTIVE', json.dumps(active_positions, ensure_ascii=False, default=str))
        return 0

    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    holdings_items = _holding_items(await client.holdings())
    open_order_items = _open_order_items(await client.orders('OPEN'))
    nonzero_holdings = _nonzero_holdings(holdings_items)
    position_qty = _symbol_position_quantity(holdings_items, symbol)
    open_buy = _has_open_buy_order(open_order_items, symbol)
    account_flat = len(nonzero_holdings) == 0 and len(open_order_items) == 0
    require_flat = os.environ.get('AUTO_TRADE_REQUIRE_ACCOUNT_FLAT', 'true').lower() == 'true'

    buying_power = unwrap(await client.buying_power('USD')) or {}
    cash_power = Decimal(str(buying_power.get('cashBuyingPower') or '0'))
    order_usd, sizing = _usd_order_size(cash_power)

    now_utc = datetime.now(timezone.utc)
    as_of = signal['as_of']
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    common = {
        'executionMode': mode,
        'signalPolicy': policy,
        'strategyVersion': signal['strategy_version'],
        'signal': signal['signal'],
        'signalAsOf': signal['as_of'],
        'signalAgeMinutes': round((now_utc - as_of).total_seconds() / 60.0, 1),
        'entryAllowed': signal['entry_allowed'],
        'riskGate': signal['risk_gate'],
        'positionState': signal['position_state'],
        'liveSignalShapeOk': _signal_shape_ok(signal, policy),
        'symbol': symbol,
        'liveSymbolAllowed': live_symbol_allowed,
        'accountFlat': account_flat,
        'requireAccountFlat': require_flat,
        'nonzeroHoldings': nonzero_holdings,
        'openOrderCount': len(open_order_items),
        'brokerHoldingQuantity': str(position_qty),
        'openBuyOrderExists': open_buy,
        'usFractionalOrderWindowOpen': window_open,
        'marketWindow': window_info,
        'liveGateOpen': settings.live_gate_open,
        'activeManagedPositions': active_positions,
        'targetExitBuckets': TARGET_EXIT_BUCKETS,
        **sizing,
    }

    if order_usd is None:
        common.update({'executionAttempted': False, 'wouldSubmit': False, 'reason': 'INSUFFICIENT_CASH_FOR_CONFIGURED_SIZE'})
        print(json.dumps(common, ensure_ascii=False, indent=2, default=str))
        return 0

    client_order_id = _client_order_id(signal['run_id'], symbol)
    request = SimpleNamespace(
        client_order_id=client_order_id,
        symbol=symbol,
        side='BUY',
        order_type='MARKET',
        time_in_force='DAY',
        quantity=None,
        order_amount=str(order_usd),
        price=None,
    )

    if mode == 'DRY_RUN':
        prepared = await prepare_order(settings, request)
        common.update({
            'executionAttempted': False,
            'wouldSubmit': False,
            'clientOrderId': client_order_id,
            'orderAmountUsd': str(order_usd),
            'estimatedNotionalKrw': prepared.estimated_notional_krw,
        })
        print(json.dumps(common, ensure_ascii=False, indent=2, default=str))
        return 0

    if not settings.live_gate_open:
        print('LIVE_GATE_CLOSED')
        return 2
    if not _signal_shape_ok(signal, policy):
        print('LIVE_SIGNAL_GATE_FAILED')
        return 2
    if not window_open:
        print('US_FRACTIONAL_ORDER_WINDOW_CLOSED')
        return 0
    if require_flat and not account_flat:
        print('ACCOUNT_NOT_FLAT')
        return 0
    if position_qty > 0:
        print('BROKER_POSITION_NOT_FLAT', symbol, position_qty)
        return 0
    if open_buy:
        print('OPEN_BUY_ORDER_EXISTS', symbol)
        return 0

    reserved, position = store.reserve_entry(
        run_id=signal['run_id'],
        symbol=symbol,
        strategy_version=signal['strategy_version'],
        signal_as_of=signal['as_of'].isoformat(),
        client_order_id=client_order_id,
        target_exit_buckets=TARGET_EXIT_BUCKETS,
    )
    if not reserved or not position:
        print('ENTRY_POSITION_RESERVATION_FAILED', json.dumps(position, ensure_ascii=False, default=str))
        return 0

    try:
        result = await execute_order(settings, request)
    except Exception as exc:
        store.mark_entry_aborted(position['position_id'], f'{type(exc).__name__}: {exc}')
        raise

    if not result.get('allowed'):
        store.mark_entry_aborted(position['position_id'], f"entry blocked: {result.get('reason')}")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    order_id = result.get('orderId')
    if not order_id:
        store.mark_ambiguous_entry(position['position_id'], 'entry submission returned no orderId')
        print('ENTRY_AMBIGUOUS_NO_ORDER_ID')
        return 2

    store.mark_entry_submitted(position['position_id'], order_id)
    result['managedPositionId'] = position['position_id']
    result['targetExitBuckets'] = TARGET_EXIT_BUCKETS
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
