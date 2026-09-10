"""Reconcile bot-managed entries and execute the frozen four-bucket exit rule.

This module never creates a new entry. It only reconciles orders previously
registered by engine.auto_trade and, in LIVE mode, submits risk-reducing exits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import TradeLedger, execute_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient

TERMINAL_STATUSES = {
    'FILLED',
    'CANCELED',
    'REJECTED',
    'REPLACED',
    'CANCEL_REJECTED',
    'REPLACE_REJECTED',
}
QTY_TOLERANCE = Decimal('0.00000001')


def _decimal(value) -> Decimal:
    return Decimal(str(value or '0'))


def _exit_client_order_id(position_id: str, attempt: int) -> str:
    digest = hashlib.sha256(f'{position_id}|EXIT|{attempt}'.encode()).hexdigest()[:14]
    return f'kalman-exit-{digest}'[:36]


def _order_view(payload) -> dict:
    data = unwrap(payload) or {}
    return data if isinstance(data, dict) else {}


def _execution(order: dict) -> dict:
    value = order.get('execution') or {}
    return value if isinstance(value, dict) else {}


def _open_order_ids(payload) -> set[str]:
    data = unwrap(payload) or {}
    if isinstance(data, dict):
        rows = data.get('orders') or data.get('items') or []
    else:
        rows = data or []
    return {str(row.get('orderId')) for row in rows if row.get('orderId')}


def _holding_quantity(payload, symbol: str) -> Decimal:
    data = unwrap(payload) or {}
    rows = data.get('items') or [] if isinstance(data, dict) else []
    total = Decimal('0')
    for row in rows:
        if str(row.get('symbol', '')).upper() == symbol.upper():
            total += _decimal(row.get('quantity'))
    return total


def _parse_signal_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _elapsed_canonical_buckets(db_url: str, entry_signal_as_of: str) -> int:
    entry_dt = _parse_signal_time(entry_signal_as_of)
    sql = """
        SELECT count(DISTINCT as_of)
        FROM strategy_signal
        WHERE market='US' AND as_of > %s
    """
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (entry_dt,))
        return int(cur.fetchone()[0] or 0)


async def _reconcile_reserved(store: ManagedPositionStore, ledger: TradeLedger, position: dict) -> dict:
    state = position['state']
    if state == 'ENTRY_RESERVED':
        guard = ledger.get(position['entry_client_order_id'])
        if guard is None:
            store.mark_entry_aborted(position['position_id'], 'entry reservation existed but executor ledger had no order attempt')
            return {'action': 'ENTRY_ABORTED_NO_ORDER_ATTEMPT'}
        if guard['status'] == 'SUBMITTED' and guard.get('toss_order_id'):
            store.mark_entry_submitted(position['position_id'], guard['toss_order_id'])
            return {'action': 'ENTRY_RECOVERED_SUBMITTED', 'orderId': guard['toss_order_id']}
        if guard['status'] == 'FAILED':
            store.mark_entry_aborted(position['position_id'], guard.get('error') or 'entry submission failed')
            return {'action': 'ENTRY_ABORTED_FAILED'}
        store.mark_ambiguous_entry(
            position['position_id'],
            f"entry executor state is ambiguous: order_guard={guard['status']}; reconcile in Toss before retry",
        )
        return {'action': 'ENTRY_AMBIGUOUS', 'ledgerStatus': guard['status']}

    if state == 'EXIT_RESERVED':
        guard = ledger.get(position['exit_client_order_id'])
        if guard is None:
            store.release_exit(position['position_id'], 'exit reservation existed but executor ledger had no order attempt', increment_attempt=False)
            return {'action': 'EXIT_RELEASED_NO_ORDER_ATTEMPT'}
        if guard['status'] == 'SUBMITTED' and guard.get('toss_order_id'):
            store.mark_exit_submitted(position['position_id'], guard['toss_order_id'])
            return {'action': 'EXIT_RECOVERED_SUBMITTED', 'orderId': guard['toss_order_id']}
        if guard['status'] == 'FAILED':
            store.release_exit(position['position_id'], guard.get('error') or 'exit submission failed')
            return {'action': 'EXIT_RELEASED_FAILED'}
        store.mark_manual_reconcile(
            position['position_id'],
            f"exit executor state is ambiguous: order_guard={guard['status']}; reconcile in Toss before retry",
        )
        return {'action': 'EXIT_AMBIGUOUS', 'ledgerStatus': guard['status']}

    return {'action': 'NO_RESERVED_RECONCILIATION'}


async def _reconcile_entry(store: ManagedPositionStore, client: TossClient, position: dict) -> dict:
    order_id = position.get('entry_order_id')
    if not order_id:
        store.mark_ambiguous_entry(position['position_id'], 'ENTRY_SUBMITTED without entry_order_id')
        return {'action': 'ENTRY_AMBIGUOUS_NO_ORDER_ID'}

    order = _order_view(await client.order(order_id))
    status = str(order.get('status') or '').upper()
    execution = _execution(order)
    filled = _decimal(execution.get('filledQuantity'))
    avg = execution.get('averageFilledPrice')

    is_terminal = status in TERMINAL_STATUSES
    if status == 'PARTIAL_FILLED':
        open_ids = _open_order_ids(await client.orders('OPEN', position['symbol']))
        is_terminal = order_id not in open_ids

    if not is_terminal:
        store.update_entry_status(position['position_id'], status or 'UNKNOWN', filled)
        return {'action': 'ENTRY_WAITING', 'status': status, 'filledQuantity': str(filled)}

    if filled <= 0:
        store.mark_entry_aborted(position['position_id'], f'entry terminal without fill: {status}')
        return {'action': 'ENTRY_ABORTED_UNFILLED', 'status': status}

    store.mark_open(position['position_id'], entry_status=status, filled_quantity=filled, average_price=avg)
    return {
        'action': 'POSITION_OPENED',
        'status': status,
        'filledQuantity': str(filled),
        'averageFilledPrice': avg,
    }


async def _reconcile_exit(store: ManagedPositionStore, client: TossClient, position: dict) -> dict:
    order_id = position.get('exit_order_id')
    if not order_id:
        store.mark_manual_reconcile(position['position_id'], 'EXIT_SUBMITTED without exit_order_id')
        return {'action': 'EXIT_AMBIGUOUS_NO_ORDER_ID'}

    order = _order_view(await client.order(order_id))
    status = str(order.get('status') or '').upper()
    execution = _execution(order)
    filled = _decimal(execution.get('filledQuantity'))
    avg = execution.get('averageFilledPrice')

    is_terminal = status in TERMINAL_STATUSES
    if status == 'PARTIAL_FILLED':
        open_ids = _open_order_ids(await client.orders('OPEN', position['symbol']))
        is_terminal = order_id not in open_ids

    if not is_terminal:
        return {'action': 'EXIT_WAITING', 'status': status, 'filledQuantity': str(filled)}

    if filled <= 0:
        store.release_exit(position['position_id'], f'exit terminal without fill: {status}')
        return {'action': 'EXIT_RELEASED_UNFILLED', 'status': status}

    updated = store.apply_exit_fill(
        position['position_id'],
        status=status,
        newly_filled_quantity=filled,
        average_price=avg,
    )
    return {
        'action': 'POSITION_CLOSED' if updated and updated['state'] == 'CLOSED' else 'EXIT_PARTIAL_TERMINAL',
        'status': status,
        'filledQuantity': str(filled),
        'remainingQuantity': updated['remaining_quantity'] if updated else None,
        'averageFilledPrice': avg,
    }


async def _manage_open_position(settings: Settings, store: ManagedPositionStore, client: TossClient, position: dict, mode: str) -> dict:
    db_url = os.environ.get('DATABASE_URL_WRITER')
    if not db_url:
        raise RuntimeError('DATABASE_URL_WRITER is missing')

    symbol = position['symbol']
    expected_qty = _decimal(position['remaining_quantity'])
    broker_qty = _holding_quantity(await client.holdings(symbol), symbol)

    if broker_qty == 0:
        store.mark_closed_manual(position['position_id'], 'broker holding is zero before managed exit; treated as manual close')
        return {'action': 'CLOSED_MANUAL_BROKER_FLAT', 'symbol': symbol}

    if abs(broker_qty - expected_qty) > QTY_TOLERANCE:
        store.mark_manual_reconcile(
            position['position_id'],
            f'broker quantity mismatch: managed={expected_qty}, broker={broker_qty}',
        )
        return {
            'action': 'MANUAL_RECONCILE_REQUIRED',
            'symbol': symbol,
            'managedQuantity': str(expected_qty),
            'brokerQuantity': str(broker_qty),
        }

    elapsed = _elapsed_canonical_buckets(db_url, position['entry_signal_as_of'])
    target = int(position['target_exit_buckets'])
    report = {
        'action': 'HOLD',
        'symbol': symbol,
        'positionId': position['position_id'],
        'entrySignalAsOf': position['entry_signal_as_of'],
        'elapsedCanonicalBuckets': elapsed,
        'targetExitBuckets': target,
        'remainingQuantity': str(expected_qty),
        'executionMode': mode,
    }
    if elapsed < target:
        return report

    window_open, window_info = await us_fractional_order_window(client)
    report.update({'exitDue': True, 'usFractionalOrderWindowOpen': window_open, 'marketWindow': window_info})
    if mode != 'LIVE':
        report['action'] = 'DRY_RUN_EXIT_DUE'
        return report
    if not settings.live_gate_open:
        report['action'] = 'LIVE_GATE_CLOSED_EXIT_PENDING'
        return report
    if not window_open:
        report['action'] = 'EXIT_WINDOW_CLOSED'
        return report

    attempt = int(position.get('exit_attempt') or 0)
    client_order_id = _exit_client_order_id(position['position_id'], attempt)
    reserved, row = store.reserve_exit(position['position_id'], client_order_id)
    if not reserved:
        return {'action': 'EXIT_RESERVATION_FAILED', 'current': row}

    request = SimpleNamespace(
        client_order_id=client_order_id,
        symbol=symbol,
        side='SELL',
        order_type='MARKET',
        time_in_force='DAY',
        quantity=str(expected_qty),
        order_amount=None,
        price=None,
    )
    try:
        result = await execute_order(settings, request, risk_reducing_exit=True)
    except Exception as exc:
        guard = TradeLedger(settings.state_db_path).get(client_order_id)
        if guard and guard.get('status') == 'AMBIGUOUS':
            store.mark_manual_reconcile(
                position['position_id'],
                f"broker exit submission ambiguous: {guard.get('error') or exc}",
            )
        else:
            store.release_exit(position['position_id'], f'{type(exc).__name__}: {exc}')
        raise

    if not result.get('allowed'):
        store.release_exit(position['position_id'], f"exit blocked: {result.get('reason')}")
        return {'action': 'EXIT_BLOCKED', 'result': result}

    order_id = result.get('orderId')
    if not order_id:
        store.mark_manual_reconcile(position['position_id'], 'exit submission returned no orderId')
        return {'action': 'EXIT_AMBIGUOUS_NO_ORDER_ID', 'result': result}

    store.mark_exit_submitted(position['position_id'], order_id)
    return {
        'action': 'EXIT_SUBMITTED',
        'positionId': position['position_id'],
        'symbol': symbol,
        'quantity': str(expected_qty),
        'clientOrderId': client_order_id,
        'orderId': order_id,
    }


async def main_async() -> int:
    load_dotenv(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env'), override=True)
    if os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() != 'true':
        print('AUTO_TRADE_DISABLED_POSITION_MANAGER')
        return 0

    mode = os.environ.get('AUTO_TRADE_EXECUTION_MODE', 'DRY_RUN').strip().upper()
    if mode not in {'DRY_RUN', 'LIVE'}:
        raise RuntimeError('AUTO_TRADE_EXECUTION_MODE must be DRY_RUN or LIVE')

    settings = Settings()
    store = ManagedPositionStore(settings.state_db_path)
    ledger = TradeLedger(settings.state_db_path)
    client = TossClient(settings)
    positions = store.active()
    if not positions:
        print('NO_MANAGED_POSITION')
        return 0

    reports = []
    for original in positions:
        position = store.get(original['position_id']) or original
        state = position['state']

        if state in {'ENTRY_RESERVED', 'EXIT_RESERVED'}:
            reports.append(await _reconcile_reserved(store, ledger, position))
            position = store.get(position['position_id']) or position
            state = position['state']

        if state == 'ENTRY_SUBMITTED':
            reports.append(await _reconcile_entry(store, client, position))
            position = store.get(position['position_id']) or position
            state = position['state']

        if state == 'EXIT_SUBMITTED':
            reports.append(await _reconcile_exit(store, client, position))
            # Never submit a second exit in the same invocation after reconciling
            # a terminal/partial order. Let broker holdings settle, then retry on
            # the next scheduled cycle if quantity remains.
            continue

        if state == 'OPEN':
            reports.append(await _manage_open_position(settings, store, client, position, mode))
        elif state in {'MANUAL_RECONCILE', 'AMBIGUOUS_ENTRY'}:
            reports.append({
                'action': 'TRADING_BLOCKED_MANUAL_RECONCILE',
                'positionId': position['position_id'],
                'symbol': position['symbol'],
                'state': state,
                'note': position.get('note'),
            })

    print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
