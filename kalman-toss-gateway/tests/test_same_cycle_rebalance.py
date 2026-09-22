from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.managed_positions import ManagedPositionStore
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

    def test_model_rotation_can_be_disabled_for_multi_position_live_policy(self):
        with patch.dict(
            position_manager.os.environ,
            {"AUTO_TRADE_MODEL_ROTATION_ENABLED": "false"},
            clear=False,
        ):
            self.assertFalse(position_manager._model_rotation_enabled())

        with patch.dict(
            position_manager.os.environ,
            {"AUTO_TRADE_MODEL_ROTATION_ENABLED": "true"},
            clear=False,
        ):
            self.assertTrue(position_manager._model_rotation_enabled())

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

    def test_distinct_symbols_can_be_managed_concurrently(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ManagedPositionStore(pathlib.Path(tmp) / "trading.sqlite3")
            first_ok, first = store.reserve_entry(
                run_id="run-a",
                symbol="AAPL",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:00:00+00:00",
                client_order_id="order-a",
                target_exit_buckets=4,
            )
            second_ok, second = store.reserve_entry(
                run_id="run-b",
                symbol="MSFT",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:05:00+00:00",
                client_order_id="order-b",
                target_exit_buckets=4,
            )
            self.assertTrue(first_ok)
            self.assertTrue(second_ok)
            self.assertEqual(first["symbol"], "AAPL")
            self.assertEqual(second["symbol"], "MSFT")

    def test_same_symbol_second_active_lot_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ManagedPositionStore(pathlib.Path(tmp) / "trading.sqlite3")
            first_ok, _ = store.reserve_entry(
                run_id="run-a",
                symbol="AAPL",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:00:00+00:00",
                client_order_id="order-a",
                target_exit_buckets=4,
            )
            second_ok, existing = store.reserve_entry(
                run_id="run-b",
                symbol="AAPL",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:05:00+00:00",
                client_order_id="order-b",
                target_exit_buckets=4,
            )
            self.assertTrue(first_ok)
            self.assertFalse(second_ok)
            self.assertEqual(existing["symbol"], "AAPL")


    def test_same_symbol_add_on_aggregates_quantity_and_weighted_average(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ManagedPositionStore(pathlib.Path(tmp) / "trading.sqlite3")
            ok, row = store.reserve_entry(
                run_id="run-a",
                symbol="AAPL",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:00:00+00:00",
                client_order_id="order-a",
                target_exit_buckets=4,
            )
            self.assertTrue(ok)
            store.mark_open(
                row["position_id"],
                entry_status="FILLED",
                filled_quantity=Decimal("1"),
                average_price="100",
            )

            ok, add_on = store.reserve_add_on(
                row["position_id"],
                run_id="run-b",
                signal_as_of="2026-09-22T01:00:00+00:00",
                client_order_id="order-b",
                target_krw="5000",
                max_entries=3,
                min_gap_minutes=60,
            )
            self.assertTrue(ok)
            self.assertEqual(add_on["state"], "ADD_ON_RESERVED")
            store.mark_add_on_submitted(row["position_id"], "toss-b")
            updated = store.apply_add_on_fill(
                row["position_id"],
                status="FILLED",
                filled_quantity=Decimal("1"),
                average_price="120",
            )

            self.assertEqual(updated["state"], "OPEN")
            self.assertEqual(updated["entry_count"], 2)
            self.assertEqual(Decimal(updated["remaining_quantity"]), Decimal("2"))
            self.assertEqual(Decimal(updated["entry_avg_fill_price"]), Decimal("110"))
            self.assertEqual(
                updated["entry_signal_as_of"],
                "2026-09-22T00:00:00+00:00",
            )
            self.assertEqual(
                updated["last_entry_signal_as_of"],
                "2026-09-22T01:00:00+00:00",
            )

    def test_add_on_requires_new_bucket_and_stops_after_three_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ManagedPositionStore(pathlib.Path(tmp) / "trading.sqlite3")
            ok, row = store.reserve_entry(
                run_id="run-a",
                symbol="AAPL",
                strategy_version="R5.1_BASE_HGB",
                signal_as_of="2026-09-22T00:00:00+00:00",
                client_order_id="order-a",
                target_exit_buckets=4,
            )
            self.assertTrue(ok)
            store.mark_open(
                row["position_id"],
                entry_status="FILLED",
                filled_quantity=Decimal("1"),
                average_price="100",
            )

            too_soon, _ = store.reserve_add_on(
                row["position_id"],
                run_id="run-b0",
                signal_as_of="2026-09-22T00:30:00+00:00",
                client_order_id="order-b0",
                target_krw="5000",
                max_entries=3,
                min_gap_minutes=60,
            )
            self.assertFalse(too_soon)

            second_ok, _ = store.reserve_add_on(
                row["position_id"],
                run_id="run-b",
                signal_as_of="2026-09-22T01:00:00+00:00",
                client_order_id="order-b",
                target_krw="5000",
                max_entries=3,
                min_gap_minutes=60,
            )
            self.assertTrue(second_ok)
            store.apply_add_on_fill(
                row["position_id"],
                status="FILLED",
                filled_quantity=Decimal("1"),
                average_price="100",
            )

            third_ok, _ = store.reserve_add_on(
                row["position_id"],
                run_id="run-c",
                signal_as_of="2026-09-22T02:00:00+00:00",
                client_order_id="order-c",
                target_krw="5000",
                max_entries=3,
                min_gap_minutes=60,
            )
            self.assertTrue(third_ok)
            store.apply_add_on_fill(
                row["position_id"],
                status="FILLED",
                filled_quantity=Decimal("1"),
                average_price="100",
            )

            fourth_ok, final = store.reserve_add_on(
                row["position_id"],
                run_id="run-d",
                signal_as_of="2026-09-22T03:00:00+00:00",
                client_order_id="order-d",
                target_krw="5000",
                max_entries=3,
                min_gap_minutes=60,
            )
            self.assertFalse(fourth_ok)
            self.assertEqual(final["entry_count"], 3)



if __name__ == '__main__':
    unittest.main()
