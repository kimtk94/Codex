from __future__ import annotations

import json
import sqlite3
import time

import httpx
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from .config import Settings
from .risk import validate_order
from .toss_client import TossClient

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class PreparedOrder:
    payload: dict
    estimated_notional_krw: int
    currency: str
    source_notional: Decimal


def _result(payload):
    if isinstance(payload, dict) and 'result' in payload:
        return payload['result']
    return payload


def _decimal(v) -> Decimal:
    return Decimal(str(v))


def _quote_telemetry(payload) -> dict:
    data = _result(payload) or {}
    if not isinstance(data, dict):
        return {}
    asks = []
    bids = []
    for row in data.get('asks') or []:
        try:
            p = _decimal(row.get('price'))
            if p > 0:
                asks.append(p)
        except Exception:
            pass
    for row in data.get('bids') or []:
        try:
            p = _decimal(row.get('price'))
            if p > 0:
                bids.append(p)
        except Exception:
            pass
    best_ask = min(asks) if asks else None
    best_bid = max(bids) if bids else None
    mid = None
    spread_bps = None
    if best_ask is not None and best_bid is not None and best_ask >= best_bid:
        mid = (best_ask + best_bid) / Decimal('2')
        if mid > 0:
            spread_bps = (best_ask - best_bid) / mid * Decimal('10000')
    return {
        'timestamp': data.get('timestamp'),
        'currency': data.get('currency'),
        'best_bid': str(best_bid) if best_bid is not None else None,
        'best_ask': str(best_ask) if best_ask is not None else None,
        'mid': str(mid) if mid is not None else None,
        'spread_bps': str(spread_bps) if spread_bps is not None else None,
    }


class TradeLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ddl = """CREATE TABLE IF NOT EXISTS order_guard (
            client_order_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            trade_date_kst TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            estimated_notional_krw INTEGER NOT NULL,
            status TEXT NOT NULL,
            toss_order_id TEXT,
            error TEXT
        )"""
        with self._connect() as conn:
            conn.execute(ddl)
            cols = {row[1] for row in conn.execute('PRAGMA table_info(order_guard)').fetchall()}
            if 'telemetry_json' not in cols:
                conn.execute('ALTER TABLE order_guard ADD COLUMN telemetry_json TEXT')

    def _connect(self):
        return sqlite3.connect(self.path, timeout=15, isolation_level=None)

    def reserve(self, client_order_id: str, symbol: str, side: str, amount_krw: int, daily_limit: int) -> tuple[bool, str, int]:
        today = datetime.now(KST).date().isoformat()
        side = side.upper()
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            dup = conn.execute('SELECT status FROM order_guard WHERE client_order_id=?', (client_order_id,)).fetchone()
            if dup:
                conn.rollback()
                return False, 'DUPLICATE_CLIENT_ORDER_ID', 0
            used = conn.execute(
                """SELECT COALESCE(SUM(estimated_notional_krw),0)
                   FROM order_guard
                   WHERE trade_date_kst=? AND side='BUY'
                     AND status IN ('RESERVED','SUBMITTED','AMBIGUOUS')""",
                (today,),
            ).fetchone()[0]
            if side == 'BUY' and int(used) + amount_krw > daily_limit:
                conn.rollback()
                return False, 'DAILY_TOTAL_LIMIT_EXCEEDED', int(used)
            conn.execute(
                """INSERT INTO order_guard (
                    client_order_id,created_at,trade_date_kst,symbol,side,
                    estimated_notional_krw,status,toss_order_id,error
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (client_order_id, datetime.now(timezone.utc).isoformat(), today, symbol, side, amount_krw, 'RESERVED', None, None),
            )
            conn.commit()
            return True, 'OK', int(used)

    def finish(self, client_order_id: str, status: str, toss_order_id: str | None = None, error: str | None = None):
        with self._connect() as conn:
            conn.execute(
                'UPDATE order_guard SET status=?, toss_order_id=?, error=? WHERE client_order_id=?',
                (status, toss_order_id, error, client_order_id),
            )

    def daily_committed(self) -> int:
        today = datetime.now(KST).date().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(estimated_notional_krw),0)
                   FROM order_guard
                   WHERE trade_date_kst=? AND side='BUY'
                     AND status IN ('RESERVED','SUBMITTED','AMBIGUOUS')""",
                (today,),
            ).fetchone()
        return int(row[0])

    def get(self, client_order_id: str) -> dict | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM order_guard WHERE client_order_id=?', (client_order_id,)).fetchone()
            return dict(row) if row else None


    def patch_telemetry(self, client_order_id: str, patch: dict) -> None:
        if not patch:
            return
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT telemetry_json FROM order_guard WHERE client_order_id=?',
                (client_order_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                return
            current = {}
            if row[0]:
                try:
                    parsed = json.loads(row[0])
                    if isinstance(parsed, dict):
                        current = parsed
                except (TypeError, ValueError, json.JSONDecodeError):
                    current = {}
            current.update(patch)
            conn.execute(
                'UPDATE order_guard SET telemetry_json=? WHERE client_order_id=?',
                (json.dumps(current, ensure_ascii=False, separators=(',', ':'), default=str), client_order_id),
            )
            conn.commit()


async def prepare_order(settings: Settings, request) -> PreparedOrder:
    symbol = request.symbol.upper()
    side = request.side.upper()
    order_type = request.order_type.upper()
    quantity = request.quantity
    order_amount = request.order_amount
    price = request.price

    if (quantity is None) == (order_amount is None):
        raise ValueError('Exactly one of quantity or order_amount is required')
    if order_type not in {'MARKET', 'LIMIT'}:
        raise ValueError('order_type must be MARKET or LIMIT')
    if side not in {'BUY', 'SELL'}:
        raise ValueError('side must be BUY or SELL')
    if order_type == 'LIMIT' and price is None:
        raise ValueError('price is required for LIMIT')
    if order_type == 'MARKET' and price is not None:
        raise ValueError('price must be omitted for MARKET')
    if order_amount is not None and (order_type != 'MARKET' or side != 'BUY'):
        raise ValueError('order_amount is restricted here to US MARKET BUY; SELL must use quantity')

    client = TossClient(settings)
    payload = {
        'clientOrderId': request.client_order_id,
        'symbol': symbol,
        'side': side,
        'orderType': order_type,
    }
    if request.time_in_force:
        payload['timeInForce'] = request.time_in_force.upper()

    if order_amount is not None:
        usd = _decimal(order_amount)
        if usd <= 0:
            raise ValueError('order_amount must be > 0')
        fx = _decimal(_result(await client.exchange_rate('USD', 'KRW'))['rate'])
        krw = int((usd * fx).quantize(Decimal('1'), rounding=ROUND_CEILING))
        payload['orderAmount'] = str(order_amount)
        currency, source_notional = 'USD', usd
    else:
        qty = _decimal(quantity)
        if qty <= 0:
            raise ValueError('quantity must be > 0')
        if order_type == 'LIMIT':
            unit = _decimal(price)
            price_payload = str(price)
            quote = _result(await client.prices([symbol]))[0]
            currency = quote['currency'].upper()
        else:
            prices = _result(await client.prices([symbol]))
            if not prices:
                raise RuntimeError(f'No price returned for {symbol}')
            quote = prices[0]
            unit = _decimal(quote['lastPrice'])
            currency = quote['currency'].upper()
            price_payload = None
        source_notional = qty * unit
        if currency == 'USD':
            fx = _decimal(_result(await client.exchange_rate('USD', 'KRW'))['rate'])
            krw = int((source_notional * fx).quantize(Decimal('1'), rounding=ROUND_CEILING))
        else:
            krw = int(source_notional.quantize(Decimal('1'), rounding=ROUND_CEILING))
        payload['quantity'] = str(quantity)
        if price_payload is not None:
            payload['price'] = price_payload

    return PreparedOrder(payload=payload, estimated_notional_krw=krw, currency=currency, source_notional=source_notional)


async def execute_order(settings: Settings, request, *, risk_reducing_exit: bool = False):
    if not request.client_order_id:
        raise ValueError('client_order_id is required for live execution')
    prepared = await prepare_order(settings, request)
    ledger = TradeLedger(settings.state_db_path)
    used = ledger.daily_committed()
    decision = validate_order(
        settings,
        request.symbol,
        prepared.estimated_notional_krw,
        used,
        risk_reducing_exit=risk_reducing_exit,
    )
    if not decision.allowed:
        return {
            'allowed': False,
            'reason': decision.reason,
            'executionAttempted': False,
            'estimatedNotionalKrw': prepared.estimated_notional_krw,
        }

    client = TossClient(settings)
    if request.side.upper() == 'BUY':
        bp = _result(await client.buying_power(prepared.currency))
        available = _decimal(bp['cashBuyingPower'])
        if available < prepared.source_notional:
            return {
                'allowed': False,
                'reason': 'INSUFFICIENT_BUYING_POWER',
                'executionAttempted': False,
                'estimatedNotionalKrw': prepared.estimated_notional_krw,
            }
    elif request.quantity is not None:
        sq = _result(await client.sellable_quantity(request.symbol))
        sellable = _decimal(sq.get('sellableQuantity', sq.get('quantity', '0')))
        if sellable < _decimal(request.quantity):
            return {
                'allowed': False,
                'reason': 'INSUFFICIENT_SELLABLE_QUANTITY',
                'executionAttempted': False,
                'estimatedNotionalKrw': prepared.estimated_notional_krw,
            }

    ok, reason, prior_used = ledger.reserve(
        request.client_order_id,
        request.symbol.upper(),
        request.side.upper(),
        prepared.estimated_notional_krw,
        settings.live_micro_total_limit_krw,
    )
    if not ok:
        return {
            'allowed': False,
            'reason': reason,
            'executionAttempted': False,
            'dailyCommittedKrw': prior_used,
        }

    try:
        quote_payload = await client.orderbook(request.symbol)
        ledger.patch_telemetry(
            request.client_order_id,
            {
                'pretrade_quote': _quote_telemetry(quote_payload),
                'pretrade_quote_response': dict(client.last_response_meta),
            },
        )
    except Exception as exc:
        ledger.patch_telemetry(
            request.client_order_id,
            {
                'pretrade_quote_error': f'{type(exc).__name__}: {exc}',
                'pretrade_quote_response': dict(client.last_response_meta),
            },
        )

    submit_started = datetime.now(timezone.utc)
    submit_clock = time.perf_counter()
    try:
        result = await client.place_order(prepared.payload)
    except httpx.HTTPStatusError as exc:
        submit_completed = datetime.now(timezone.utc)
        ledger.patch_telemetry(request.client_order_id, {'submit': {
            'started_at': submit_started.isoformat(),
            'completed_at': submit_completed.isoformat(),
            'http_latency_ms': round((time.perf_counter() - submit_clock) * 1000, 3),
            'response_meta': dict(client.last_response_meta),
        }})
        status = exc.response.status_code if exc.response is not None else 0
        ledger.finish(
            request.client_order_id,
            'FAILED' if 400 <= status < 500 else 'AMBIGUOUS',
            error=f'{type(exc).__name__}: HTTP {status}: {exc}',
        )
        raise
    except (httpx.TransportError, TimeoutError) as exc:
        submit_completed = datetime.now(timezone.utc)
        ledger.patch_telemetry(request.client_order_id, {'submit': {
            'started_at': submit_started.isoformat(),
            'completed_at': submit_completed.isoformat(),
            'http_latency_ms': round((time.perf_counter() - submit_clock) * 1000, 3),
            'response_meta': dict(client.last_response_meta),
        }})
        ledger.finish(request.client_order_id, 'AMBIGUOUS', error=f'{type(exc).__name__}: {exc}')
        raise
    except Exception as exc:
        submit_completed = datetime.now(timezone.utc)
        ledger.patch_telemetry(request.client_order_id, {'submit': {
            'started_at': submit_started.isoformat(),
            'completed_at': submit_completed.isoformat(),
            'http_latency_ms': round((time.perf_counter() - submit_clock) * 1000, 3),
            'response_meta': dict(client.last_response_meta),
        }})
        ledger.finish(request.client_order_id, 'AMBIGUOUS', error=f'{type(exc).__name__}: {exc}')
        raise

    submit_completed = datetime.now(timezone.utc)
    ledger.patch_telemetry(request.client_order_id, {'submit': {
        'started_at': submit_started.isoformat(),
        'completed_at': submit_completed.isoformat(),
        'http_latency_ms': round((time.perf_counter() - submit_clock) * 1000, 3),
        'response_meta': dict(client.last_response_meta),
    }})

    inner = _result(result) or {}
    order_id = inner.get('orderId') if isinstance(inner, dict) else None
    if not order_id:
        ledger.finish(
            request.client_order_id,
            'AMBIGUOUS',
            error='Toss returned success without orderId; manual reconciliation required',
        )
        raise RuntimeError('Toss order response missing orderId')

    ledger.finish(request.client_order_id, 'SUBMITTED', order_id)
    return {
        'allowed': True,
        'reason': 'SUBMITTED',
        'executionAttempted': True,
        'estimatedNotionalKrw': prepared.estimated_notional_krw,
        'clientOrderId': request.client_order_id,
        'orderId': order_id,
        'order': result,
    }
