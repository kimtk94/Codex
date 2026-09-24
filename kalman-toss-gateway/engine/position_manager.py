"""Reconcile bot-managed entries and execute guarded live exit rules.

This module never creates a new entry. It only reconciles orders previously
registered by engine.auto_trade and, in LIVE mode, submits risk-reducing exits.

When a due LIVE exit is submitted, the manager performs a short bounded poll
for terminal fill confirmation. A fully closed position can therefore release
the same run_auto_trade.sh lock cycle to engine.auto_trade for a fresh entry.
Unfilled, partial, ambiguous, or timed-out exits remain active and keep entries
blocked.
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
from app.live_exit_policy import (
    choose_exit_reason as choose_live_exit_reason,
    should_clear_profit_flip_pending,
    validate_profit_flip_parameters,
)
from app.market_guard import unwrap, us_fractional_order_window
from app.prospective_shadow import ProspectiveShadowConfig, ProspectiveShadowStore
from app.toss_client import TossClient
from engine.prospective_shadow import manage_prospective_shadows

TERMINAL_STATUSES = {
    'FILLED',
    'CANCELED',
    'REJECTED',
    'REPLACED',
    'CANCEL_REJECTED',
    'REPLACE_REJECTED',
}
QTY_TOLERANCE = Decimal('0.00000001')
DEFAULT_EXIT_FILL_WAIT_SECONDS = 45.0
DEFAULT_EXIT_POLL_SECONDS = 1.0


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


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _broker_order_telemetry(order: dict, response_meta: dict | None = None) -> dict:
    execution = _execution(order)
    ordered_at = _optional_datetime(order.get('orderedAt'))
    filled_at = _optional_datetime(execution.get('filledAt'))
    fill_latency_ms = None
    if ordered_at is not None and filled_at is not None:
        fill_latency_ms = max(0.0, (filled_at - ordered_at).total_seconds() * 1000.0)
    return {
        'order_id': order.get('orderId'),
        'status': str(order.get('status') or '').upper() or None,
        'currency': order.get('currency'),
        'ordered_at': order.get('orderedAt'),
        'canceled_at': order.get('canceledAt'),
        'filled_quantity': execution.get('filledQuantity'),
        'average_filled_price': execution.get('averageFilledPrice'),
        'filled_amount': execution.get('filledAmount'),
        'commission': execution.get('commission'),
        'tax': execution.get('tax'),
        'filled_at': execution.get('filledAt'),
        'settlement_date': execution.get('settlementDate'),
        'broker_fill_latency_ms': round(fill_latency_ms, 3) if fill_latency_ms is not None else None,
        'response_meta': dict(response_meta or {}),
    }


def _persist_broker_order_telemetry(client: TossClient, position: dict, leg: str, order: dict) -> None:
    if leg == 'ENTRY':
        client_order_id = position.get('entry_client_order_id')
    elif leg == 'ADD_ON':
        client_order_id = position.get('add_on_client_order_id')
    else:
        client_order_id = position.get('exit_client_order_id')
    settings = getattr(client, 'settings', None)
    if not client_order_id or settings is None:
        return
    TradeLedger(settings.state_db_path).patch_telemetry(
        client_order_id,
        {'broker_order': _broker_order_telemetry(order, getattr(client, 'last_response_meta', {}))},
    )


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


def _latest_eligible_signal(db_url: str, strategy_version: str, policy: str) -> dict | None:
    where = [
        "s.market='US'",
        "s.strategy_version=%s",
        "d.status='READY'",
        "d.stale_after > now()",
    ]
    params: list[object] = [strategy_version]
    if policy == 'SHADOW_CANARY':
        where.extend([
            "s.signal='SHADOW'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'",
            "lower(COALESCE(s.payload->>'shadow_entry_this_signal','false'))='true'",
        ])
    elif policy == 'R5_LIVE_TOP1':
        where.extend([
            "s.signal='SHADOW'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'",
        ])
    else:
        where.extend([
            "s.signal='BUY'",
            "s.entry_allowed IS TRUE",
            "upper(COALESCE(s.risk_gate,''))='PASS'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'live_execution','false'))='true'",
        ])
    sql = f"""
        SELECT s.symbol,s.as_of,s.run_id
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
        return {'symbol': str(row[0]).upper(), 'as_of': row[1], 'run_id': row[2]}


async def _last_price(client: TossClient, symbol: str) -> Decimal:
    payload = unwrap(await client.prices([symbol])) or []
    rows = payload if isinstance(payload, list) else payload.get('items', []) if isinstance(payload, dict) else []
    if not rows:
        raise RuntimeError(f'No current price returned for {symbol}')
    price = _decimal(rows[0].get('lastPrice'))
    if price <= 0:
        raise RuntimeError(f'Invalid current price returned for {symbol}')
    return price


def _exit_thresholds() -> tuple[Decimal, Decimal]:
    stop_loss = Decimal(os.environ.get('AUTO_TRADE_STOP_LOSS_PCT', '-0.03'))
    take_profit = Decimal(os.environ.get('AUTO_TRADE_TAKE_PROFIT_PCT', '0.20'))
    if stop_loss >= 0 or stop_loss < Decimal('-0.50'):
        raise RuntimeError('AUTO_TRADE_STOP_LOSS_PCT must be between -0.50 and 0')
    if take_profit <= 0 or take_profit > Decimal('5'):
        raise RuntimeError('AUTO_TRADE_TAKE_PROFIT_PCT must be > 0 and <= 5')
    return stop_loss, take_profit


def _model_rotation_enabled() -> bool:
    return (
        os.environ.get('AUTO_TRADE_MODEL_ROTATION_ENABLED', 'true').strip().lower() == 'true'
    )


def _profit_flip_config() -> tuple[bool, Decimal, Decimal, Decimal, int]:
    enabled = (
        os.environ.get('AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED', 'false').strip().lower()
        == 'true'
    )
    arm_pct = Decimal(os.environ.get('AUTO_TRADE_PROFIT_FLIP_ARM_PCT', '0.002'))
    trigger_pct = Decimal(os.environ.get('AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT', '-0.002'))
    recovery_pct = Decimal(os.environ.get('AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT', '0'))
    try:
        confirm = int(os.environ.get('AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS', '2'))
    except ValueError as exc:
        raise RuntimeError(
            'AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS must be an integer'
        ) from exc

    validate_profit_flip_parameters(
        arm_pct=arm_pct,
        trigger_pct=trigger_pct,
        recovery_pct=recovery_pct,
        confirm_observations=confirm,
    )
    return enabled, arm_pct, trigger_pct, recovery_pct, confirm


def _choose_exit_reason(
    *,
    price_return: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    model_rotation: bool,
    elapsed_buckets: int,
    target_buckets: int,
    pending_exit_reason: str | None = None,
) -> str | None:
    return choose_live_exit_reason(
        price_return=price_return,
        stop_loss=stop_loss,
        take_profit=take_profit,
        model_rotation=model_rotation,
        elapsed_buckets=elapsed_buckets,
        target_buckets=target_buckets,
        pending_exit_reason=pending_exit_reason,
    )


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

    if state == 'ADD_ON_RESERVED':
        guard = ledger.get(position['add_on_client_order_id'])
        if guard is None:
            store.release_add_on(
                position['position_id'],
                'add-on reservation existed but executor ledger had no order attempt',
            )
            return {'action': 'ADD_ON_RELEASED_NO_ORDER_ATTEMPT'}
        if guard['status'] == 'SUBMITTED' and guard.get('toss_order_id'):
            store.mark_add_on_submitted(position['position_id'], guard['toss_order_id'])
            return {'action': 'ADD_ON_RECOVERED_SUBMITTED', 'orderId': guard['toss_order_id']}
        if guard['status'] == 'FAILED':
            store.release_add_on(
                position['position_id'],
                guard.get('error') or 'add-on submission failed',
            )
            return {'action': 'ADD_ON_RELEASED_FAILED'}
        store.mark_ambiguous_add_on(
            position['position_id'],
            f"add-on executor state is ambiguous: order_guard={guard['status']}; reconcile in Toss before retry",
        )
        return {'action': 'ADD_ON_AMBIGUOUS', 'ledgerStatus': guard['status']}

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
    _persist_broker_order_telemetry(client, position, 'ENTRY', order)
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


async def _reconcile_add_on(store: ManagedPositionStore, client: TossClient, position: dict) -> dict:
    order_id = position.get('add_on_order_id')
    if not order_id:
        store.mark_ambiguous_add_on(position['position_id'], 'ADD_ON_SUBMITTED without add_on_order_id')
        return {'action': 'ADD_ON_AMBIGUOUS_NO_ORDER_ID'}

    order = _order_view(await client.order(order_id))
    _persist_broker_order_telemetry(client, position, 'ADD_ON', order)
    status = str(order.get('status') or '').upper()
    execution = _execution(order)
    filled = _decimal(execution.get('filledQuantity'))
    avg = execution.get('averageFilledPrice')

    is_terminal = status in TERMINAL_STATUSES
    if status == 'PARTIAL_FILLED':
        open_ids = _open_order_ids(await client.orders('OPEN', position['symbol']))
        is_terminal = order_id not in open_ids

    if not is_terminal:
        store.update_add_on_status(position['position_id'], status or 'UNKNOWN')
        return {'action': 'ADD_ON_WAITING', 'status': status, 'filledQuantity': str(filled)}

    if filled <= 0:
        store.release_add_on(position['position_id'], f'add-on terminal without fill: {status}')
        return {'action': 'ADD_ON_RELEASED_UNFILLED', 'status': status}

    try:
        updated = store.apply_add_on_fill(
            position['position_id'],
            status=status,
            filled_quantity=filled,
            average_price=avg,
        )
    except ValueError as exc:
        store.mark_ambiguous_add_on(position['position_id'], str(exc))
        return {'action': 'ADD_ON_MANUAL_RECONCILE', 'reason': str(exc)}

    return {
        'action': 'ADD_ON_APPLIED',
        'status': status,
        'filledQuantity': str(filled),
        'averageFilledPrice': avg,
        'entryCount': updated['entry_count'] if updated else None,
        'aggregateQuantity': updated['remaining_quantity'] if updated else None,
        'aggregateAveragePrice': updated['entry_avg_fill_price'] if updated else None,
    }


async def _reconcile_exit(store: ManagedPositionStore, client: TossClient, position: dict) -> dict:
    order_id = position.get('exit_order_id')
    if not order_id:
        store.mark_manual_reconcile(position['position_id'], 'EXIT_SUBMITTED without exit_order_id')
        return {'action': 'EXIT_AMBIGUOUS_NO_ORDER_ID'}

    order = _order_view(await client.order(order_id))
    _persist_broker_order_telemetry(client, position, 'EXIT', order)
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


def _exit_wait_config() -> tuple[float, float]:
    try:
        wait_seconds = float(
            os.environ.get('AUTO_TRADE_EXIT_FILL_WAIT_SECONDS', str(DEFAULT_EXIT_FILL_WAIT_SECONDS))
        )
        poll_seconds = float(
            os.environ.get('AUTO_TRADE_EXIT_POLL_SECONDS', str(DEFAULT_EXIT_POLL_SECONDS))
        )
    except ValueError as exc:
        raise RuntimeError('exit fill wait settings must be numeric') from exc

    if wait_seconds < 0 or wait_seconds > 120:
        raise RuntimeError('AUTO_TRADE_EXIT_FILL_WAIT_SECONDS must be between 0 and 120')
    if poll_seconds <= 0 or poll_seconds > 10:
        raise RuntimeError('AUTO_TRADE_EXIT_POLL_SECONDS must be > 0 and <= 10')
    return wait_seconds, poll_seconds


async def _wait_for_exit_terminal(
    store: ManagedPositionStore,
    client: TossClient,
    position_id: str,
    *,
    wait_seconds: float,
    poll_seconds: float,
) -> dict:
    """Bounded same-cycle reconciliation for a freshly submitted exit."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    polls = 0
    last_report: dict = {'action': 'EXIT_WAITING'}

    while True:
        position = store.get(position_id)
        if not position:
            return {
                'action': 'EXIT_POLL_POSITION_MISSING',
                'positionId': position_id,
                'pollCount': polls,
            }

        state = str(position.get('state') or '').upper()
        if state != 'EXIT_SUBMITTED':
            return {
                'action': 'EXIT_POLL_COMPLETE',
                'positionId': position_id,
                'positionState': state,
                'pollCount': polls,
                'lastReport': last_report,
            }

        last_report = await _reconcile_exit(store, client, position)
        polls += 1
        if last_report.get('action') != 'EXIT_WAITING':
            refreshed = store.get(position_id) or {}
            return {
                'action': 'EXIT_POLL_COMPLETE',
                'positionId': position_id,
                'positionState': str(refreshed.get('state') or '').upper(),
                'pollCount': polls,
                'lastReport': last_report,
            }

        remaining = deadline - loop.time()
        if remaining <= 0:
            return {
                'action': 'EXIT_POLL_TIMEOUT',
                'positionId': position_id,
                'pollCount': polls,
                'waitSeconds': wait_seconds,
                'lastReport': last_report,
            }
        await asyncio.sleep(min(poll_seconds, remaining))


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

    entry_price = _decimal(position.get('entry_avg_fill_price'))
    if entry_price <= 0:
        store.mark_manual_reconcile(position['position_id'], 'missing valid entry average fill price')
        return {'action': 'MANUAL_RECONCILE_REQUIRED', 'symbol': symbol, 'reason': 'MISSING_ENTRY_PRICE'}

    last_price = await _last_price(client, symbol)
    price_return = last_price / entry_price - Decimal('1')
    stop_loss, take_profit = _exit_thresholds()

    (
        flip_enabled,
        flip_arm_pct,
        flip_trigger_pct,
        flip_recovery_pct,
        flip_confirm_observations,
    ) = _profit_flip_config()
    observed_guard = None
    pending_exit_reason = position.get('exit_pending_reason')
    if flip_enabled:
        observed_guard = store.observe_price_return(
            position['position_id'],
            price_return=price_return,
            arm_pct=flip_arm_pct,
            trigger_pct=flip_trigger_pct,
            confirm_observations=flip_confirm_observations,
        )
        if observed_guard:
            pending_exit_reason = observed_guard.get('exit_pending_reason')

        # Daytime deterioration only prepares an exit. At execution time the
        # position is revalidated against the latest price; a recovery above
        # the configured threshold cancels the pending exit.
        if should_clear_profit_flip_pending(
            pending_reason=pending_exit_reason,
            price_return=price_return,
            recovery_pct=flip_recovery_pct,
        ):
            store.clear_exit_pending(position['position_id'])
            pending_exit_reason = None
            observed_guard = store.get(position['position_id'])

    elapsed = _elapsed_canonical_buckets(db_url, position['entry_signal_as_of'])
    target = int(position['target_exit_buckets'])
    policy = os.environ.get('AUTO_TRADE_SIGNAL_POLICY', 'APPROVED_ONLY').strip().upper()
    latest = _latest_eligible_signal(db_url, position['strategy_version'], policy)
    entry_as_of = _parse_signal_time(position['entry_signal_as_of'])
    rotation_enabled = _model_rotation_enabled()
    rotation = bool(
        rotation_enabled
        and latest
        and latest['as_of'] > entry_as_of
        and latest['symbol'] != symbol.upper()
    )

    exit_reason = _choose_exit_reason(
        price_return=price_return,
        stop_loss=stop_loss,
        take_profit=take_profit,
        model_rotation=rotation,
        elapsed_buckets=elapsed,
        target_buckets=target,
        pending_exit_reason=pending_exit_reason,
    )

    report = {
        'action': 'HOLD',
        'symbol': symbol,
        'positionId': position['position_id'],
        'entrySignalAsOf': position['entry_signal_as_of'],
        'entryAveragePrice': str(entry_price),
        'lastPrice': str(last_price),
        'priceReturn': str(price_return),
        'stopLossPct': str(stop_loss),
        'takeProfitPct': str(take_profit),
        'elapsedCanonicalBuckets': elapsed,
        'targetExitBuckets': target,
        'latestEligibleSymbol': latest['symbol'] if latest else None,
        'latestEligibleAsOf': latest['as_of'] if latest else None,
        'modelRotationEnabled': rotation_enabled,
        'modelRotation': rotation,
        'remainingQuantity': str(expected_qty),
        'executionMode': mode,
        'profitFlipGuardEnabled': flip_enabled,
        'profitFlipArmPct': str(flip_arm_pct),
        'profitFlipTriggerPct': str(flip_trigger_pct),
        'profitFlipRecoveryPct': str(flip_recovery_pct),
        'profitFlipConfirmObservations': flip_confirm_observations,
        'profitFlipArmed': bool(
            int((observed_guard or position).get('profit_flip_armed') or 0)
        ),
        'profitFlipNegativeObservations': int(
            (observed_guard or position).get('profit_flip_negative_count') or 0
        ),
        'peakPriceReturn': (observed_guard or position).get('peak_price_return'),
        'pendingExitReason': pending_exit_reason,
        'pendingExitSince': (observed_guard or position).get('exit_pending_since'),
        'exitReason': exit_reason,
    }
    if not exit_reason:
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
        report['action'] = (
            'EXIT_PENDING_WINDOW_CLOSED'
            if exit_reason == 'PROFIT_TO_LOSS_FLIP'
            else 'EXIT_WINDOW_CLOSED'
        )
        return report

    attempt = int(position.get('exit_attempt') or 0)
    client_order_id = _exit_client_order_id(position['position_id'], attempt)
    reserved, row = store.reserve_exit(position['position_id'], client_order_id)
    if not reserved:
        return {'action': 'EXIT_RESERVATION_FAILED', 'current': row, 'exitReason': exit_reason}

    store.set_exit_reason(position['position_id'], exit_reason)

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
        return {'action': 'EXIT_BLOCKED', 'result': result, 'exitReason': exit_reason}

    order_id = result.get('orderId')
    if not order_id:
        store.mark_manual_reconcile(position['position_id'], 'exit submission returned no orderId')
        return {'action': 'EXIT_AMBIGUOUS_NO_ORDER_ID', 'result': result, 'exitReason': exit_reason}

    store.mark_exit_submitted(position['position_id'], order_id)
    return {
        'action': 'EXIT_SUBMITTED',
        'positionId': position['position_id'],
        'symbol': symbol,
        'quantity': str(expected_qty),
        'clientOrderId': client_order_id,
        'orderId': order_id,
        'exitReason': exit_reason,
        'priceReturn': str(price_return),
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

    shadow_config = ProspectiveShadowConfig.from_env()
    shadow_store = (
        ProspectiveShadowStore(settings.state_db_path)
        if shadow_config.enabled
        else None
    )

    positions = store.active()
    if not positions and not (
        shadow_store and shadow_store.has_open(shadow_config.candidate_id)
    ):
        print('NO_MANAGED_POSITION')
        return 0

    reports = []
    shadow_price_overrides: dict[str, Decimal] = {}

    for original in positions:
        position = store.get(original['position_id']) or original
        state = position['state']

        if state in {'ENTRY_RESERVED', 'ADD_ON_RESERVED', 'EXIT_RESERVED'}:
            reports.append(await _reconcile_reserved(store, ledger, position))
            position = store.get(position['position_id']) or position
            state = position['state']

        if state == 'ENTRY_SUBMITTED':
            reports.append(await _reconcile_entry(store, client, position))
            position = store.get(position['position_id']) or position
            state = position['state']

        if state == 'ADD_ON_SUBMITTED':
            reports.append(await _reconcile_add_on(store, client, position))
            position = store.get(position['position_id']) or position
            state = position['state']

        if state == 'EXIT_SUBMITTED':
            reports.append(await _reconcile_exit(store, client, position))
            # Never submit a second exit in the same invocation after reconciling
            # a terminal/partial order. Let broker holdings settle, then retry on
            # the next scheduled cycle if quantity remains.
            continue

        if state == 'OPEN':
            if shadow_store:
                shadow_store.seed_or_sync(position, shadow_config)

            open_report = await _manage_open_position(settings, store, client, position, mode)
            reports.append(open_report)

            if open_report.get('lastPrice') not in (None, ''):
                try:
                    shadow_price_overrides[position['position_id']] = Decimal(
                        str(open_report['lastPrice'])
                    )
                except Exception:
                    pass

            if (
                shadow_store
                and mode == 'LIVE'
                and open_report.get('action') == 'EXIT_SUBMITTED'
                and open_report.get('lastPrice') not in (None, '')
                and open_report.get('priceReturn') not in (None, '')
                and open_report.get('exitReason')
            ):
                shadow_store.record_live_policy_exit_reference(
                    shadow_config.candidate_id,
                    position['position_id'],
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    price=Decimal(str(open_report['lastPrice'])),
                    price_return=Decimal(str(open_report['priceReturn'])),
                    reason=str(open_report['exitReason']),
                )

            if mode == 'LIVE' and open_report.get('action') == 'EXIT_SUBMITTED':
                wait_seconds, poll_seconds = _exit_wait_config()
                reports.append(
                    await _wait_for_exit_terminal(
                        store,
                        client,
                        position['position_id'],
                        wait_seconds=wait_seconds,
                        poll_seconds=poll_seconds,
                    )
                )
        elif state in {'MANUAL_RECONCILE', 'AMBIGUOUS_ENTRY'}:
            reports.append({
                'action': 'TRADING_BLOCKED_MANUAL_RECONCILE',
                'positionId': position['position_id'],
                'symbol': position['symbol'],
                'state': state,
                'note': position.get('note'),
            })

    if shadow_store:
        db_url = os.environ.get('DATABASE_URL_WRITER')
        if not db_url:
            raise RuntimeError('DATABASE_URL_WRITER is missing')

        shadow_reports = await manage_prospective_shadows(
            config=shadow_config,
            shadow_store=shadow_store,
            managed_store=store,
            client=client,
            db_url=db_url,
            elapsed_buckets_fn=_elapsed_canonical_buckets,
            price_overrides=shadow_price_overrides,
            watch_source=os.environ.get('KALMAN_WATCH_SOURCE'),
        )
        reports.append({
            'action': 'PROSPECTIVE_SHADOW_CYCLE',
            'candidateId': shadow_config.candidate_id,
            'candidateFingerprint': shadow_config.fingerprint,
            'brokerOrderAttempted': False,
            'summary': shadow_store.summary(shadow_config.candidate_id),
            'reports': shadow_reports,
        })

    print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
