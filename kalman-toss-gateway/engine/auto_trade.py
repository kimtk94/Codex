"""Strict DB-to-Toss live execution bridge.

No inference happens here. This worker only consumes an already-approved strategy_signal row.
It therefore cannot promote a SHADOW model by itself.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import execute_order


def _client_order_id(run_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f'{run_id}|{symbol}|BUY'.encode()).hexdigest()[:12]
    clean_symbol = ''.join(c for c in symbol.upper() if c.isalnum() or c in '-_')[:8]
    return f'kalman-{clean_symbol}-{digest}'[:36]


def load_approved_signal():
    db_url = os.environ.get('DATABASE_URL_WRITER')
    if not db_url:
        raise RuntimeError('DATABASE_URL_WRITER is missing')
    max_age = int(os.environ.get('AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES', '90'))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age)
    sql = """
        SELECT s.run_id,s.symbol,s.as_of,s.strategy_version,s.signal,s.entry_allowed,
               s.risk_gate,s.position_state,s.payload,d.stale_after,d.status
        FROM strategy_signal s
        JOIN dashboard_snapshot d ON d.run_id=s.run_id AND d.market=s.market
        WHERE s.market='US'
          AND s.signal='BUY'
          AND s.entry_allowed IS TRUE
          AND upper(COALESCE(s.risk_gate,''))='PASS'
          AND s.as_of >= %s
          AND d.status='READY'
          AND d.stale_after > now()
        ORDER BY s.as_of DESC
        LIMIT 1
    """
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (cutoff,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


async def main_async():
    load_dotenv(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env'), override=False)
    if os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() != 'true':
        print('AUTO_TRADE_DISABLED')
        return 0

    settings = Settings()
    signal = load_approved_signal()
    if not signal:
        print('NO_APPROVED_LIVE_SIGNAL')
        return 0

    symbol = signal['symbol'].upper()
    if symbol not in settings.allowed_symbols:
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
    result = await execute_order(settings, request)
    print(result)
    return 0


def main():
    return asyncio.run(main_async())


if __name__ == '__main__':
    raise SystemExit(main())
