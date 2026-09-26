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
from app.executor import TradeLedger, execute_order, prepare_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient

TARGET_EXIT_BUCKETS = 4
QTY_TOLERANCE = Decimal('0.00000001')


def _client_order_id(run_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f'{run_id}|{symbol}|BUY'.encode()).hexdigest()[:12]
    clean_symbol = ''.join(c for c in symbol.upper() if c.isalnum() or c in '-_')[:8]
    return f'kalman-{clean_symbol}-{digest}'[:36]


def _bool(value) -> bool:
    return str(value or '').strip().lower() == 'true'


def _signal_bar_minutes(strategy_version: str | None) -> int:
    """Minutes represented by a signal timestamp that marks the bar START.

    R5.1 signals are stamped at the start of a completed 60m canonical bucket.
    Freshness must therefore be measured from bar completion (as_of + 60m),
    while the stored as_of itself remains immutable for model/ledger lineage.
    """
    default = '60' if strategy_version == 'R5.1_BASE_HGB' else '0'
    raw = os.environ.get('AUTO_TRADE_SIGNAL_BAR_MINUTES', default)
    try:
        minutes = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('AUTO_TRADE_SIGNAL_BAR_MINUTES must be an integer') from exc
    if minutes < 0 or minutes > 240:
        raise RuntimeError('AUTO_TRADE_SIGNAL_BAR_MINUTES must be between 0 and 240')
    if strategy_version == 'R5.1_BASE_HGB' and minutes != 60:
        raise RuntimeError('R5.1_BASE_HGB requires AUTO_TRADE_SIGNAL_BAR_MINUTES=60')
    return minutes


def _effective_signal_as_of(as_of: datetime, strategy_version: str | None) -> datetime:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of + timedelta(minutes=_signal_bar_minutes(strategy_version))


def _max_active_positions() -> int:
    raw = os.environ.get('AUTO_TRADE_MAX_ACTIVE_POSITIONS', '3')
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('AUTO_TRADE_MAX_ACTIVE_POSITIONS must be an integer') from exc
    if value < 1 or value > 20:
        raise RuntimeError('AUTO_TRADE_MAX_ACTIVE_POSITIONS must be between 1 and 20')
    return value


def _max_entries_per_symbol() -> int:
    raw = os.environ.get('AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL', '1')
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL must be an integer') from exc
    if value < 1 or value > 10:
        raise RuntimeError('AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL must be between 1 and 10')
    return value


def _add_on_min_bucket_gap() -> int:
    raw = os.environ.get('AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP', '1')
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP must be an integer') from exc
    if value < 1 or value > 24:
        raise RuntimeError('AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP must be between 1 and 24')
    return value


def _max_symbol_notional_krw() -> Decimal:
    try:
        value = Decimal(os.environ.get('AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW', '0'))
    except Exception as exc:
        raise RuntimeError('AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW must be numeric') from exc
    if value < 0:
        raise RuntimeError('AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW must be >= 0')
    return value


def _safe_exit_window_enabled() -> bool:
    return os.environ.get('AUTO_TRADE_SAFE_EXIT_WINDOW_ENABLED', 'true').strip().lower() == 'true'


def _exit_window_buffer_minutes() -> int:
    raw = os.environ.get('AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES', '15')
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES must be an integer') from exc
    if value < 0 or value > 120:
        raise RuntimeError('AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES must be between 0 and 120')
    return value


def _as_aware_datetime(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _entry_exit_window_check(
    window_info: dict,
    *,
    anchor_signal_as_of,
    strategy_version: str | None,
    target_exit_buckets: int,
) -> tuple[bool, dict]:
    enabled = _safe_exit_window_enabled()
    buffer_minutes = _exit_window_buffer_minutes()
    detail = {
        'enabled': enabled,
        'bufferMinutes': buffer_minutes,
        'targetExitBuckets': int(target_exit_buckets),
    }
    if not enabled:
        detail['reason'] = 'DISABLED'
        return True, detail

    bar_minutes = _signal_bar_minutes(strategy_version)
    detail['signalBarMinutes'] = bar_minutes
    if bar_minutes <= 0:
        detail['reason'] = 'NO_CANONICAL_BAR_DURATION'
        return True, detail

    active = (window_info or {}).get('activeWindow') or {}
    fractional_end_text = active.get('fractionalOrderEndTime')
    if not fractional_end_text:
        detail['reason'] = 'NO_ACTIVE_FRACTIONAL_WINDOW'
        return False, detail

    anchor_as_of = _as_aware_datetime(anchor_signal_as_of)
    effective_anchor = _effective_signal_as_of(anchor_as_of, strategy_version)
    projected_exit = effective_anchor + timedelta(
        minutes=bar_minutes * int(target_exit_buckets)
    )
    fractional_end = _as_aware_datetime(fractional_end_text)
    safe_deadline = fractional_end - timedelta(minutes=buffer_minutes)
    allowed = projected_exit <= safe_deadline
    detail.update({
        'reason': 'SAFE' if allowed else 'PROJECTED_EXIT_AFTER_SAFE_DEADLINE',
        'anchorSignalAsOf': anchor_as_of.isoformat(),
        'effectiveAnchorAt': effective_anchor.isoformat(),
        'projectedMaxHoldExitAt': projected_exit.isoformat(),
        'fractionalOrderEndAt': fractional_end.isoformat(),
        'safeExitDeadlineAt': safe_deadline.isoformat(),
    })
    return allowed, detail


def _signal_gap_minutes(position: dict, signal_as_of: datetime) -> float | None:
    raw = position.get('last_entry_signal_as_of') or position.get('entry_signal_as_of')
    if not raw:
        return None
    try:
        previous = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if signal_as_of.tzinfo is None:
        signal_as_of = signal_as_of.replace(tzinfo=timezone.utc)
    return (signal_as_of - previous).total_seconds() / 60.0


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
    if policy == 'R5_LIVE_TOP1':
        # LIVE portfolio policy deliberately decouples execution from the
        # research-only 4-bar non-overlap ledger. The research flag remains
        # attached to the signal for A/B attribution and audit.
        return (
            str(signal.get('signal', '')).upper() == 'SHADOW'
            and _bool(payload.get('allow_trade_shadow'))
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
    bar_minutes = _signal_bar_minutes(strategy_version)

    where = [
        "s.market='US'",
        "(s.as_of + (%s * interval '1 minute')) >= %s",
        "d.status='READY'",
        'd.stale_after > now()',
    ]
    params: list[object] = [bar_minutes, cutoff]

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
    elif mode == 'LIVE' and policy == 'R5_LIVE_TOP1':
        where.extend([
            "s.signal='SHADOW'",
            "upper(COALESCE(s.position_state,''))='FLAT'",
            "lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'",
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


def _usd_order_size(
    cash_buying_power: Decimal,
    *,
    usd_krw_rate: Decimal | None = None,
) -> tuple[Decimal | None, dict]:
    mode = os.environ.get('AUTO_TRADE_SIZING_MODE', 'FIXED_USD').strip().upper()
    reserve = Decimal(os.environ.get('AUTO_TRADE_CASH_RESERVE_USD', '0'))
    minimum = Decimal(os.environ.get('AUTO_TRADE_MIN_ORDER_USD', '1'))
    maximum = Decimal(os.environ.get('AUTO_TRADE_MAX_ORDER_USD', '0'))
    spendable = max(Decimal('0'), cash_buying_power - reserve)

    target_krw = None
    if mode == 'FIXED_USD':
        raw = Decimal(os.environ.get('AUTO_TRADE_ORDER_USD', '2'))
    elif mode == 'FIXED_KRW':
        target_krw = Decimal(os.environ.get('AUTO_TRADE_ORDER_KRW', '5000'))
        if target_krw <= 0:
            raise RuntimeError('AUTO_TRADE_ORDER_KRW must be > 0')
        if usd_krw_rate is None or usd_krw_rate <= 0:
            raise RuntimeError('USD/KRW rate is required for FIXED_KRW sizing')
        # Toss amount orders are submitted in USD. Round down to cents so the
        # pre-submit KRW estimate never intentionally exceeds the KRW target.
        raw = (target_krw / usd_krw_rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    elif mode == 'CASH_FRACTION':
        fraction = Decimal(os.environ.get('AUTO_TRADE_CASH_FRACTION', '0.10'))
        if fraction <= 0 or fraction > 1:
            raise RuntimeError('AUTO_TRADE_CASH_FRACTION must be > 0 and <= 1')
        raw = spendable * fraction
    else:
        raise RuntimeError('AUTO_TRADE_SIZING_MODE must be FIXED_USD, FIXED_KRW or CASH_FRACTION')

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
        'targetOrderKrw': str(target_krw) if target_krw is not None else None,
        'usdKrwRateForSizing': str(usd_krw_rate) if usd_krw_rate is not None else None,
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
    if policy not in {'APPROVED_ONLY', 'SHADOW_CANARY', 'R5_LIVE_TOP1'}:
        raise RuntimeError(
            'AUTO_TRADE_SIGNAL_POLICY must be APPROVED_ONLY, SHADOW_CANARY or R5_LIVE_TOP1'
        )

    strategy_version = os.environ.get('AUTO_TRADE_STRATEGY_VERSION', '').strip() or None
    if mode == 'LIVE' and not strategy_version:
        print('LIVE_STRATEGY_VERSION_NOT_LOCKED')
        return 2
    if mode == 'LIVE' and policy == 'SHADOW_CANARY':
        if os.environ.get('AUTO_TRADE_SHADOW_CONFIRM', '') != 'CONFIRM_SHADOW_CANARY':
            print('SHADOW_CANARY_CONFIRMATION_MISSING')
            return 2
    if mode == 'LIVE' and policy == 'R5_LIVE_TOP1':
        if os.environ.get('AUTO_TRADE_OVERLAP_CONFIRM', '') != 'CONFIRM_R5_LIVE_TOP1':
            print('R5_LIVE_TOP1_CONFIRMATION_MISSING')
            return 2

    settings = Settings()
    signal = load_signal(mode, strategy_version, policy)
    if not signal:
        print('NO_ELIGIBLE_SIGNAL')
        return 0

    symbol = signal['symbol'].upper()

    store = ManagedPositionStore(settings.state_db_path)
    active_positions = store.active()
    max_active_positions = _max_active_positions()
    max_entries_per_symbol = _max_entries_per_symbol()
    add_on_min_bucket_gap = _add_on_min_bucket_gap()
    max_symbol_notional_krw = _max_symbol_notional_krw()
    same_symbol_position = next(
        (p for p in active_positions if str(p.get('symbol', '')).upper() == symbol),
        None,
    )

    # Existing managed positions no longer block a new entry globally. The
    # broker cash check, same-symbol position/open-order guards, and
    # ManagedPositionStore idempotency remain authoritative.
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
    sizing_mode = os.environ.get('AUTO_TRADE_SIZING_MODE', 'FIXED_USD').strip().upper()
    usd_krw_rate = None
    if sizing_mode == 'FIXED_KRW':
        fx_payload = unwrap(await client.exchange_rate('USD', 'KRW')) or {}
        usd_krw_rate = Decimal(str(fx_payload.get('rate') or '0'))
    order_usd, sizing = _usd_order_size(cash_power, usd_krw_rate=usd_krw_rate)

    now_utc = datetime.now(timezone.utc)
    as_of = signal['as_of']
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    bar_minutes = _signal_bar_minutes(signal.get('strategy_version'))
    effective_as_of = _effective_signal_as_of(as_of, signal.get('strategy_version'))

    entry_count_before = int((same_symbol_position or {}).get('entry_count') or 0)
    is_add_on = bool(same_symbol_position and policy == 'R5_LIVE_TOP1')
    signal_gap_minutes = (
        _signal_gap_minutes(same_symbol_position, as_of) if same_symbol_position else None
    )
    required_add_on_gap_minutes = add_on_min_bucket_gap * max(1, bar_minutes)
    target_order_krw = Decimal(os.environ.get('AUTO_TRADE_ORDER_KRW', '0'))
    projected_symbol_notional_krw = (
        target_order_krw * Decimal(entry_count_before + 1)
        if is_add_on and sizing_mode == 'FIXED_KRW'
        else None
    )

    exit_priority_states = {'EXIT_RESERVED', 'EXIT_SUBMITTED', 'MANUAL_RECONCILE'}
    exit_priority_positions = [
        p for p in active_positions
        if p.get('exit_pending_reason')
        or str(p.get('state') or '').upper() in exit_priority_states
    ]
    exit_anchor_as_of = (
        (same_symbol_position or {}).get('entry_signal_as_of')
        if is_add_on
        else signal['as_of']
    )
    entry_exit_window_ok, entry_exit_window = _entry_exit_window_check(
        window_info,
        anchor_signal_as_of=exit_anchor_as_of,
        strategy_version=signal.get('strategy_version'),
        target_exit_buckets=TARGET_EXIT_BUCKETS,
    )

    common = {
        'executionMode': mode,
        'signalPolicy': policy,
        'strategyVersion': signal['strategy_version'],
        'signal': signal['signal'],
        'signalAsOf': signal['as_of'],
        'signalTimestampSemantics': 'BAR_START' if bar_minutes else 'EVENT_TIME',
        'signalBarMinutes': bar_minutes,
        'signalAvailableAt': effective_as_of,
        'signalAgeMinutesRaw': round((now_utc - as_of).total_seconds() / 60.0, 1),
        'signalAgeMinutes': round((now_utc - effective_as_of).total_seconds() / 60.0, 1),
        'entryAllowed': signal['entry_allowed'],
        'riskGate': signal['risk_gate'],
        'positionState': signal['position_state'],
        'liveSignalShapeOk': _signal_shape_ok(signal, policy),
        'researchNonOverlapEntry': _bool((signal.get('payload') or {}).get('shadow_entry_this_signal')),
        'allowTradeShadow': _bool((signal.get('payload') or {}).get('allow_trade_shadow')),
        'symbol': symbol,
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
        'activeManagedPositionCount': len(active_positions),
        'maxActivePositions': max_active_positions,
        'sameSymbolManagedPositionId': (same_symbol_position or {}).get('position_id'),
        'sameSymbolExitPendingReason': (same_symbol_position or {}).get('exit_pending_reason'),
        'entryType': 'ADD_ON' if is_add_on else 'INITIAL',
        'entryCountBefore': entry_count_before,
        'maxEntriesPerSymbol': max_entries_per_symbol,
        'addOnMinBucketGap': add_on_min_bucket_gap,
        'signalGapMinutesFromLastEntry': signal_gap_minutes,
        'requiredAddOnGapMinutes': required_add_on_gap_minutes,
        'maxSymbolNotionalKrw': str(max_symbol_notional_krw),
        'projectedSymbolNotionalKrw': (
            str(projected_symbol_notional_krw)
            if projected_symbol_notional_krw is not None else None
        ),
        'targetExitBuckets': TARGET_EXIT_BUCKETS,
        'exitPriorityBlocking': bool(exit_priority_positions),
        'exitPriorityPositions': [
            {
                'positionId': p.get('position_id'),
                'symbol': p.get('symbol'),
                'state': p.get('state'),
                'pendingExitReason': p.get('exit_pending_reason'),
                'pendingExitSince': p.get('exit_pending_since'),
            }
            for p in exit_priority_positions
        ],
        'safeExitWindow': entry_exit_window,
        **sizing,
    }

    if mode == 'LIVE' and exit_priority_positions:
        common.update({
            'executionAttempted': False,
            'wouldSubmit': False,
            'reason': 'ENTRY_BLOCKED_PENDING_EXIT_PRIORITY',
        })
        print(json.dumps(common, ensure_ascii=False, indent=2, default=str))
        return 0

    if mode == 'LIVE' and window_open and not entry_exit_window_ok:
        common.update({
            'executionAttempted': False,
            'wouldSubmit': False,
            'reason': 'ENTRY_BLOCKED_UNSAFE_EXIT_WINDOW',
        })
        print(json.dumps(common, ensure_ascii=False, indent=2, default=str))
        return 0

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
    if open_buy:
        print('OPEN_BUY_ORDER_EXISTS', symbol)
        return 0

    if is_add_on:
        if same_symbol_position['state'] != 'OPEN':
            print('ADD_ON_POSITION_NOT_OPEN', symbol, same_symbol_position['state'])
            return 0
        if same_symbol_position.get('exit_pending_reason'):
            print(
                'ADD_ON_BLOCKED_EXIT_PENDING',
                symbol,
                same_symbol_position.get('exit_pending_reason'),
            )
            return 0
        if entry_count_before >= max_entries_per_symbol:
            print('MAX_ENTRIES_PER_SYMBOL_REACHED', symbol, entry_count_before, max_entries_per_symbol)
            return 0
        if signal_gap_minutes is None or signal_gap_minutes < required_add_on_gap_minutes:
            print(
                'ADD_ON_SIGNAL_GAP_TOO_SMALL',
                symbol,
                signal_gap_minutes,
                required_add_on_gap_minutes,
            )
            return 0
        managed_qty = Decimal(str(same_symbol_position.get('remaining_quantity') or '0'))
        if position_qty <= 0 or abs(position_qty - managed_qty) > QTY_TOLERANCE:
            print('ADD_ON_BROKER_QUANTITY_MISMATCH', symbol, position_qty, managed_qty)
            return 0
        if (
            projected_symbol_notional_krw is not None
            and max_symbol_notional_krw > 0
            and projected_symbol_notional_krw > max_symbol_notional_krw
        ):
            print(
                'MAX_SYMBOL_NOTIONAL_REACHED',
                symbol,
                projected_symbol_notional_krw,
                max_symbol_notional_krw,
            )
            return 0

        reserved, position = store.reserve_add_on(
            same_symbol_position['position_id'],
            run_id=signal['run_id'],
            signal_as_of=signal['as_of'].isoformat(),
            client_order_id=client_order_id,
            target_krw=(
                str(target_order_krw) if sizing_mode == 'FIXED_KRW' else None
            ),
            max_entries=max_entries_per_symbol,
            min_gap_minutes=required_add_on_gap_minutes,
        )
        if not reserved or not position:
            print('ADD_ON_POSITION_RESERVATION_FAILED', json.dumps(position, ensure_ascii=False, default=str))
            return 0
    else:
        if same_symbol_position:
            print('SAME_SYMBOL_ACTIVE_POSITION_POLICY_BLOCK', symbol, same_symbol_position['state'])
            return 0
        if len(active_positions) >= max_active_positions:
            print('MAX_ACTIVE_POSITIONS_REACHED', len(active_positions), max_active_positions)
            return 0
        if position_qty > 0:
            print('BROKER_POSITION_NOT_FLAT', symbol, position_qty)
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
        guard = TradeLedger(settings.state_db_path).get(client_order_id)
        if is_add_on:
            if guard and guard.get('status') == 'AMBIGUOUS':
                store.mark_ambiguous_add_on(
                    position['position_id'],
                    f"broker add-on submission ambiguous: {guard.get('error') or exc}",
                )
            else:
                store.release_add_on(position['position_id'], f'{type(exc).__name__}: {exc}')
        elif guard and guard.get('status') == 'AMBIGUOUS':
            store.mark_ambiguous_entry(
                position['position_id'],
                f"broker submission ambiguous: {guard.get('error') or exc}",
            )
        else:
            store.mark_entry_aborted(position['position_id'], f'{type(exc).__name__}: {exc}')
        raise

    if not result.get('allowed'):
        if is_add_on:
            store.release_add_on(position['position_id'], f"add-on blocked: {result.get('reason')}")
        else:
            store.mark_entry_aborted(position['position_id'], f"entry blocked: {result.get('reason')}")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    TradeLedger(settings.state_db_path).patch_telemetry(
        client_order_id,
        {
            'signal_context': {
                'execution_mode': mode,
                'signal_policy': policy,
                'strategy_version': signal['strategy_version'],
                'run_id': signal['run_id'],
                'signal_as_of': signal['as_of'].isoformat(),
                'symbol': symbol,
                'allow_trade_shadow': _bool((signal.get('payload') or {}).get('allow_trade_shadow')),
                'research_non_overlap_entry': _bool(
                    (signal.get('payload') or {}).get('shadow_entry_this_signal')
                ),
                'max_active_positions': max_active_positions,
                'active_positions_before_entry': len(active_positions),
                'entry_type': 'ADD_ON' if is_add_on else 'INITIAL',
                'entry_count_before': entry_count_before,
                'max_entries_per_symbol': max_entries_per_symbol,
                'max_symbol_notional_krw': str(max_symbol_notional_krw),
                'projected_symbol_notional_krw': (
                    str(projected_symbol_notional_krw)
                    if projected_symbol_notional_krw is not None else None
                ),
            }
        },
    )

    order_id = result.get('orderId')
    if not order_id:
        if is_add_on:
            store.mark_ambiguous_add_on(position['position_id'], 'add-on submission returned no orderId')
            print('ADD_ON_AMBIGUOUS_NO_ORDER_ID')
        else:
            store.mark_ambiguous_entry(position['position_id'], 'entry submission returned no orderId')
            print('ENTRY_AMBIGUOUS_NO_ORDER_ID')
        return 2

    if is_add_on:
        store.mark_add_on_submitted(position['position_id'], order_id)
    else:
        store.mark_entry_submitted(position['position_id'], order_id)
    result['managedPositionId'] = position['position_id']
    result['entryType'] = 'ADD_ON' if is_add_on else 'INITIAL'
    result['entryCountBefore'] = entry_count_before
    result['entryCountAfterFillExpected'] = entry_count_before + 1
    result['targetExitBuckets'] = TARGET_EXIT_BUCKETS
    result['researchNonOverlapEntry'] = _bool(
        (signal.get('payload') or {}).get('shadow_entry_this_signal')
    )
    result['liveEntryPolicy'] = policy
    result['activePositionsBeforeEntry'] = len(active_positions)
    result['maxActivePositions'] = max_active_positions
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
