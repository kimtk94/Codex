from __future__ import annotations

import pathlib
import sys
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import position_manager


class _FakeStore:
    def __init__(self, state: str = 'EXIT_SUBMITTED'):
        self.row = {
            'position_id': 'pos-test',
            'state': state,
            'symbol': 'AAPL',
            'exit_order_id': 'order-1',
        }

    def get(self, position_id: str):
        if position_id != self.row['position_id']:
            return None
        return dict(self.row)


class SameCycleRebalanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_exit_releases_position_in_same_cycle(self):
        store = _FakeStore()

        async def reconcile(fake_store, _client, _position):
            fake_store.row['state'] = 'CLOSED'
            return {
                'action': 'POSITION_CLOSED',
                'status': 'FILLED',
                'filledQuantity': '1',
                'remainingQuantity': '0',
            }

        with patch.object(position_manager, '_reconcile_exit', side_effect=reconcile) as mocked:
            report = await position_manager._wait_for_exit_terminal(
                store,
                object(),
                'pos-test',
                wait_seconds=1,
                poll_seconds=0.01,
            )

        self.assertEqual(report['action'], 'EXIT_POLL_COMPLETE')
        self.assertEqual(report['positionState'], 'CLOSED')
        self.assertEqual(report['lastReport']['action'], 'POSITION_CLOSED')
        self.assertEqual(mocked.call_count, 1)

    async def test_unresolved_exit_times_out_and_remains_blocking(self):
        store = _FakeStore()
        waiting = {
            'action': 'EXIT_WAITING',
            'status': 'SUBMITTED',
            'filledQuantity': '0',
        }

        with patch.object(
            position_manager,
            '_reconcile_exit',
            new=AsyncMock(return_value=waiting),
        ) as mocked:
            report = await position_manager._wait_for_exit_terminal(
                store,
                object(),
                'pos-test',
                wait_seconds=0,
                poll_seconds=0.01,
            )

        self.assertEqual(report['action'], 'EXIT_POLL_TIMEOUT')
        self.assertEqual(store.row['state'], 'EXIT_SUBMITTED')
        self.assertEqual(report['lastReport']['action'], 'EXIT_WAITING')
        self.assertEqual(mocked.call_count, 1)

    def test_exit_rule_priority_and_thresholds(self):
        choose = position_manager._choose_exit_reason

        self.assertEqual(
            choose(
                price_return=Decimal('-0.04'),
                stop_loss=Decimal('-0.03'),
                take_profit=Decimal('0.20'),
                model_rotation=True,
                elapsed_buckets=5,
                target_buckets=4,
            ),
            'STOP_LOSS_3PCT',
        )
        self.assertEqual(
            choose(
                price_return=Decimal('0.25'),
                stop_loss=Decimal('-0.03'),
                take_profit=Decimal('0.20'),
                model_rotation=True,
                elapsed_buckets=5,
                target_buckets=4,
            ),
            'TAKE_PROFIT_20PCT',
        )
        self.assertEqual(
            choose(
                price_return=Decimal('0.01'),
                stop_loss=Decimal('-0.03'),
                take_profit=Decimal('0.20'),
                model_rotation=True,
                elapsed_buckets=5,
                target_buckets=4,
            ),
            'MODEL_ROTATION',
        )
        self.assertEqual(
            choose(
                price_return=Decimal('0.01'),
                stop_loss=Decimal('-0.03'),
                take_profit=Decimal('0.20'),
                model_rotation=False,
                elapsed_buckets=4,
                target_buckets=4,
            ),
            'MAX_HOLD_4_BUCKETS',
        )
        self.assertIsNone(
            choose(
                price_return=Decimal('0.01'),
                stop_loss=Decimal('-0.03'),
                take_profit=Decimal('0.20'),
                model_rotation=False,
                elapsed_buckets=3,
                target_buckets=4,
            )
        )

    def test_exit_wait_config_is_bounded(self):
        with patch.dict(
            position_manager.os.environ,
            {
                'AUTO_TRADE_EXIT_FILL_WAIT_SECONDS': '45',
                'AUTO_TRADE_EXIT_POLL_SECONDS': '1',
            },
            clear=False,
        ):
            self.assertEqual(position_manager._exit_wait_config(), (45.0, 1.0))

        with patch.dict(
            position_manager.os.environ,
            {'AUTO_TRADE_EXIT_FILL_WAIT_SECONDS': '121'},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, 'between 0 and 120'):
                position_manager._exit_wait_config()


if __name__ == '__main__':
    unittest.main()
