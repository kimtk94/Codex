"""Strict DB-to-Toss automated execution bridge.

The worker has two explicit modes:
- DRY_RUN: read-only broker/account checks plus order preview. Never submits.
- LIVE: requires an exact approved strategy version and all live gates.

No inference or SHADOW->LIVE promotion happens here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import execute_order, prepare_order
from app.toss_client import TossClient

KST = timezone(timedelta(hours=9))


def _unwrap(payload):
    if isinstance(payload, dict) and 'result' in payload:
        return payload['result']
    return payload


def _client_order_id(run_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f'{run_id}|{symbol}|BUY'.encode()).hexdigest()[:12]
    clean_symbol = ''.join(c for c in symbol.upper() if c.isalnum() or c in '-_')[:8]
    return f'kalman-{clean_symbol}-{digest}'[:36]


def _live_signal_shape_ok(signal: dict) -> bool:
    payload = signal.get('payload') or {}
    return (
        str(signal.get('signal', '')).upper() == 'BUY'
        and signal.get('entry_allowed') is True
        and str(signal.get('risk_gate', '')).upper() == 'PASS'
        and str(signal.get('position_state', '')).upper() == 'FLAT'
        and str(payload.get('live_execution', False)).lower() == 'true'
    )


def load_signal(mode: str, strategy_version: str | None):
    db_url = os.environ.get('DATABASE_URL_WRITER')
    if not db_url:
        raise RuntimeError('DATABASE_URL_WRITER is missing')

    # LIVE keeps the strict freshness gate. DRY_RUN gets a separate, wider
    # inspection window so broker plumbing can be tested before the US session
    # without weakening any live-execution condition.
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

    if mode == 'LIVE':
        where.extend([
            "s.signal='BUY'",
            's.entry_allowed IS TRUE',
            "upper(COALESCE(s.risk_gate,''))='PASS'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'live_execution','false'))='true'",
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


async def _us_amount_order_window(client: TossClient) -> tuple[bool, dict]:
    calendar = _unwrap(await client.market_calendar_us()) or {}
    now = datetime.now(KST)
    windows = []
    for key in ('previousBusinessDay', 'today', 'nextBusinessDay'):
        day = calendar.get(key) or {}
        regular = day.get('regularMarket') or {}
        start_text = regular.get('startTime')
        end_text = regular.get('endTime')
        if not start_text or not end_text:
            continue
        start = datetime.fromisoformat(start_text)
        regular_end = datetime.fromisoformat(end_text)
        amount_order_end = regular_end - timedelta(hours=1)
        item = {
            'businessDate': day.get('date'),
            'startTime': start.isoformat(),
            'amountOrderEndTime': amount_order_end.isoformat(),
            'regularEndTime': regular_end.isoformat(),
        }
        windows.append(item)
        if start <= now < amount_order_end:
            return True, {'nowKst': now.isoformat(), 'activeWindow': item, 'windows': windows}
    return False, {'nowKst': now.isoformat(), 'activeWindow': None, 'windows': windows}


def _holding_items(payload) -> list[dict]:
    data = _unwrap(payload) or {}
    return list(data.get('items') or []) if isinstance(data, dict) else []


def _open_order_items(payload) -> list[dict]:
    data = _unwrap(payload) or {}
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


async def main_async():
    load_dotenv(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env'), override=True)

    if os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() != 'true':
        print('AUTO_TRADE_DISABLED')
        return 0

    mode = os.environ.get('AUTO_TRADE_EXECUTION_MODE', 'DRY_RUN').strip().upper()
    if mode not in {'DRY_RUN', 'LIVE'}:
        raise RuntimeError('AUTO_TRADE_EXECUTION_MODE must be DRY_RUN or LIVE')

    strategy_version = os.environ.get('AUTO_TRADE_STRATEGY_VERSION', '').strip() or None
    if mode == 'LIVE' and not strategy_version:
        print('LIVE_STRATEGY_VERSION_NOT_LOCKED')
        return 2

    settings = Settings()
    signal = load_signal(mode, strategy_version)
    if not signal:
        print('NO_ELIGIBLE_SIGNAL')
        return 0

    symbol = signal['symbol'].upper()
    live_symbol_allowed = symbol in settings.allowed_symbols
    if mode == 'LIVE' and not live_symbol_allowed:
        print('SIGNAL_SYMBOL_NOT_ALLOWED', symbol)
        return 0

    order_usd = os.environ.get('AUTO_TRADE_ORDER_USD', '2')
    request = SimpleNamespace(
        client_order_id=_client_order_id(signal['run_id'], symbol),
        symbol=symbol,
        side='BUY',
        order_type='MARKET',
        time_in_force='DAY',
        quantity=None,
        order_amount=order_usd,
        price=None,
    )

    client = TossClient(settings)
    window_open, window_info = await _us_amount_order_window(client)
    holdings_items = _holding_items(await client.holdings())
    open_order_items = _open_order_items(await client.orders('OPEN'))
    nonzero_holdings = _nonzero_holdings(holdings_items)
    position_qty = _symbol_position_quantity(holdings_items, symbol)
    open_buy = _has_open_buy_order(open_order_items, symbol)
    account_flat = len(nonzero_holdings) == 0 and len(open_order_items) == 0

    if mode == 'DRY_RUN':
        prepared = await prepare_order(settings, request)
        buying_power = _unwrap(await client.buying_power(prepared.currency)) or {}
        now_utc = datetime.now(timezone.utc)
        as_of = signal['as_of']
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        report = {
            'executionMode': 'DRY_RUN',
            'executionAttempted': False,
            'wouldSubmit': False,
            'strategyVersion': signal['strategy_version'],
            'signal': signal['signal'],
            'signalAsOf': signal['as_of'],
            'signalAgeMinutes': round((now_utc - as_of).total_seconds() / 60.0, 1),
            'entryAllowed': signal['entry_allowed'],
            'riskGate': signal['risk_gate'],
            'positionState': signal['position_state'],
            'liveSignalShapeOk': _live_signal_shape_ok(signal),
            'symbol': symbol,
            'liveSymbolAllowed': live_symbol_allowed,
            'clientOrderId': request.client_order_id,
            'orderAmountUsd': str(order_usd),
            'estimatedNotionalKrw': prepared.estimated_notional_krw,
            'cashBuyingPower': buying_power.get('cashBuyingPower'),
            'accountFlat': account_flat,
            'nonzeroHoldings': nonzero_holdings,
            'openOrderCount': len(open_order_items),
            'brokerHoldingQuantity': str(position_qty),
            'openBuyOrderExists': open_buy,
            'usAmountOrderWindowOpen': window_open,
            'marketWindow': window_info,
            'liveGateOpen': settings.live_gate_open,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    if not settings.live_gate_open:
        print('LIVE_GATE_CLOSED')
        return 2
    if not _live_signal_shape_ok(signal):
        print('LIVE_SIGNAL_GATE_FAILED')
        return 2
    if not window_open:
        print('US_AMOUNT_ORDER_WINDOW_CLOSED')
        return 0
    if os.environ.get('AUTO_TRADE_REQUIRE_ACCOUNT_FLAT', 'true').lower() == 'true' and not account_flat:
        print('BROKER_ACCOUNT_NOT_FLAT')
        print(json.dumps({'nonzeroHoldings': nonzero_holdings, 'openOrderCount': len(open_order_items)}, ensure_ascii=False))
        return 0
    if position_qty > 0:
        print('BROKER_POSITION_NOT_FLAT', symbol, position_qty)
        return 0
    if open_buy:
        print('OPEN_BUY_ORDER_EXISTS', symbol)
        return 0

    result = await execute_order(settings, request)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main():
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
