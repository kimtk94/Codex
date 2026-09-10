from __future__ import annotations

import sqlite3

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
                'INSERT INTO order_guard VALUES (?,?,?,?,?,?,?,?,?)',
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
        result = await client.place_order(prepared.payload)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        ledger.finish(
            request.client_order_id,
            'FAILED' if 400 <= status < 500 else 'AMBIGUOUS',
            error=f'{type(exc).__name__}: HTTP {status}: {exc}',
        )
        raise
    except (httpx.TransportError, TimeoutError) as exc:
        ledger.finish(request.client_order_id, 'AMBIGUOUS', error=f'{type(exc).__name__}: {exc}')
        raise
    except Exception as exc:
        ledger.finish(request.client_order_id, 'AMBIGUOUS', error=f'{type(exc).__name__}: {exc}')
        raise

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
