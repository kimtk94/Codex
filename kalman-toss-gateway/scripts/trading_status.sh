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
        'signalBarMinutes': int(os.environ.get('AUTO_TRADE_SIGNAL_BAR_MINUTES', '0') or 0),
        'maxSignalAgeMinutes': int(os.environ.get('AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES', '90') or 90),
        'maxActivePositions': int(os.environ.get('AUTO_TRADE_MAX_ACTIVE_POSITIONS', '3') or 3),
        'maxEntriesPerSymbol': int(os.environ.get('AUTO_TRADE_MAX_ENTRIES_PER_SYMBOL', '1') or 1),
        'addOnMinBucketGap': int(os.environ.get('AUTO_TRADE_ADD_ON_MIN_BUCKET_GAP', '1') or 1),
        'maxSymbolNotionalKrw': os.environ.get('AUTO_TRADE_MAX_SYMBOL_NOTIONAL_KRW', '0'),
        'orderKrw': os.environ.get('AUTO_TRADE_ORDER_KRW', '0'),
        'modelRotationEnabled': os.environ.get('AUTO_TRADE_MODEL_ROTATION_ENABLED', 'true').lower() == 'true',
        'profitFlipGuardEnabled': os.environ.get('AUTO_TRADE_PROFIT_FLIP_GUARD_ENABLED', 'false').lower() == 'true',
        'profitFlipArmPct': os.environ.get('AUTO_TRADE_PROFIT_FLIP_ARM_PCT', '0.002'),
        'profitFlipTriggerPct': os.environ.get('AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT', '-0.002'),
        'profitFlipRecoveryPct': os.environ.get('AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT', '0'),
        'profitFlipConfirmObservations': int(os.environ.get('AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS', '2') or 2),
        'researchNonOverlapBenchmark': True,
        'liveEntryRequiresResearchNonOverlap': (
            os.environ.get('AUTO_TRADE_SIGNAL_POLICY', 'APPROVED_ONLY').upper() == 'SHADOW_CANARY'
        ),
        'liveGateOpen': s.live_gate_open,
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
