#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${KALMAN_APP_ROOT:-/opt/kalman/app}"
ENV_FILE="${KALMAN_ENV_FILE:-/opt/kalman/.env}"
PY="${KALMAN_PYTHON:-/opt/kalman/.venv/bin/python}"
export KALMAN_ENV_FILE="$ENV_FILE"
cd "$APP_ROOT"

"$PY" - <<'PY'
from __future__ import annotations
import asyncio, json, os
from dotenv import load_dotenv

load_dotenv(os.environ['KALMAN_ENV_FILE'], override=True)
from app.config import Settings
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap
from app.toss_client import TossClient

async def main():
    s = Settings()
    store = ManagedPositionStore(s.state_db_path)
    report = {
        'autoTradeEnabled': os.environ.get('AUTO_TRADE_ENABLED', 'false').lower() == 'true',
        'executionMode': os.environ.get('AUTO_TRADE_EXECUTION_MODE', 'DRY_RUN').upper(),
        'signalPolicy': os.environ.get('AUTO_TRADE_SIGNAL_POLICY', 'APPROVED_ONLY').upper(),
        'strategyVersion': os.environ.get('AUTO_TRADE_STRATEGY_VERSION', ''),
        'liveGateOpen': s.live_gate_open,
        'allowedSymbols': sorted(s.allowed_symbols),
        'activeManagedPositions': store.active(),
        'recentManagedPositions': store.recent(10),
    }
    try:
        c = TossClient(s)
        holdings = unwrap(await c.holdings()) or {}
        orders = unwrap(await c.orders('OPEN')) or {}
        buying = unwrap(await c.buying_power('USD')) or {}
        report['broker'] = {
            'holdings': holdings.get('items', []) if isinstance(holdings, dict) else holdings,
            'openOrders': orders.get('orders', []) if isinstance(orders, dict) else orders,
            'cashBuyingPowerUsd': buying.get('cashBuyingPower') if isinstance(buying, dict) else None,
        }
    except Exception as exc:
        report['brokerError'] = f'{type(exc).__name__}: {exc}'
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

asyncio.run(main())
PY
