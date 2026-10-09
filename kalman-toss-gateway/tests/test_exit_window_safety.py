from __future__ import annotations

import asyncio
import io
import pathlib
import sys
import tempfile
import unittest
from decimal import Decimal
from datetime import datetime, timezone
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.managed_positions import ManagedPositionStore
from engine import auto_trade


class FrozenFridayDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        frozen = datetime(2026, 9, 25, 14, 35, tzinfo=timezone.utc)
        return frozen.astimezone(tz) if tz is not None else frozen.replace(tzinfo=None)


class ExitWindowSafetyTests(unittest.TestCase):
    def _window(self) -> dict:
        return {
            'nowKst': '2026-09-25T23:35:00+09:00',
            'activeWindow': {
                'businessDate': '2026-09-25',
                'startTime': '2026-09-25T22:30:00+09:00',
                'fractionalOrderEndTime': '2026-09-26T04:00:00+09:00',
                'regularEndTime': '2026-09-26T05:00:00+09:00',
            },
            'windows': [],
        }

    def test_friday_entry_before_deadline_keeps_four_buckets(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_FRIDAY_FLAT_ENABLED': 'true',
                'AUTO_TRADE_FRIDAY_FLAT_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            # Reproduce the window's fixed 2026-09-25 clock rather than
            # comparing a historical fixture to today's wall-clock time.
            with patch.object(auto_trade, 'datetime', FrozenFridayDatetime):
                allowed, detail = auto_trade._entry_exit_window_check(
                    self._window(),
                    anchor_signal_as_of='2026-09-25T17:30:00+00:00',
                    strategy_version='R5.1_BASE_HGB',
                    target_exit_buckets=4,
                )

        self.assertTrue(allowed)
        self.assertEqual(detail['reason'], 'FRIDAY_ENTRY_SAFE')
        self.assertEqual(detail['selectedTargetExitBuckets'], 4)
        self.assertEqual(
            detail['effectiveAnchorAt'],
            '2026-09-25T18:30:00+00:00',
        )
        self.assertEqual(
            detail['safeExitDeadlineAt'],
            '2026-09-26T03:45:00+09:00',
        )

    def test_friday_entry_after_deadline_is_blocked(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_FRIDAY_FLAT_ENABLED': 'true',
                'AUTO_TRADE_FRIDAY_FLAT_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            allowed, detail = auto_trade._entry_exit_window_check(
                self._window(),
                anchor_signal_as_of='2026-09-25T18:30:00+00:00',
                strategy_version='R5.1_BASE_HGB',
                target_exit_buckets=4,
            )

        self.assertFalse(allowed)
        self.assertEqual(detail['reason'], 'FRIDAY_ENTRY_AFTER_SAFE_DEADLINE')
        self.assertEqual(detail['selectedTargetExitBuckets'], 4)

    def test_non_friday_keeps_fixed4_carry(self):
        window = self._window()
        window['activeWindow'] = dict(window['activeWindow'])
        window['activeWindow']['businessDate'] = '2026-09-30'
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_FRIDAY_FLAT_ENABLED': 'true',
                'AUTO_TRADE_FRIDAY_FLAT_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            allowed, detail = auto_trade._entry_exit_window_check(
                window,
                anchor_signal_as_of='2026-09-30T18:30:00+00:00',
                strategy_version='R5.1_BASE_HGB',
                target_exit_buckets=4,
            )

        self.assertTrue(allowed)
        self.assertEqual(detail['reason'], 'NON_FRIDAY_CARRY_ALLOWED')
        self.assertEqual(detail['selectedTargetExitBuckets'], 4)

    def test_friday_flat_buffer_is_validated(self):
        with patch.dict(
            auto_trade.os.environ,
            {'AUTO_TRADE_FRIDAY_FLAT_BUFFER_MINUTES': '121'},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, 'between 0 and 120'):
                auto_trade._friday_flat_buffer_minutes()

    def test_add_on_uses_original_position_clock_but_keeps_four_buckets(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_FRIDAY_FLAT_ENABLED': 'true',
                'AUTO_TRADE_FRIDAY_FLAT_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            # Reproduce the window's fixed 2026-09-25 clock rather than
            # comparing a historical fixture to today's wall-clock time.
            with patch.object(auto_trade, 'datetime', FrozenFridayDatetime):
                allowed, detail = auto_trade._entry_exit_window_check(
                    self._window(),
                    anchor_signal_as_of='2026-09-25T13:30:00+00:00',
                    strategy_version='R5.1_BASE_HGB',
                    target_exit_buckets=4,
                )

        self.assertTrue(allowed)
        self.assertEqual(detail['selectedTargetExitBuckets'], 4)

    def test_live_pending_exit_blocks_before_signal_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'trading.sqlite3'
            store = ManagedPositionStore(db)
            ok, row = store.reserve_entry(
                run_id='run-block',
                symbol='QCOM',
                strategy_version='R5.1_BASE_HGB',
                signal_as_of='2026-09-25T14:30:00+00:00',
                client_order_id='order-block',
                target_exit_buckets=4,
            )
            self.assertTrue(ok)
            store.mark_open(
                row['position_id'],
                entry_status='FILLED',
                filled_quantity=Decimal('1'),
                average_price='200',
            )
            store.set_exit_pending(row['position_id'], 'MAX_HOLD_4_BUCKETS')

            fake_settings = SimpleNamespace(
                state_db_path=db,
                live_gate_open=True,
            )
            signal_lookup = Mock(side_effect=AssertionError('signal lookup must not run'))

            env = {
                'KALMAN_ENV_FILE': str(pathlib.Path(tmp) / 'missing.env'),
                'AUTO_TRADE_ENABLED': 'true',
                'AUTO_TRADE_EXECUTION_MODE': 'LIVE',
                'AUTO_TRADE_SIGNAL_POLICY': 'R5_LIVE_TOP1',
                'AUTO_TRADE_STRATEGY_VERSION': 'R5.1_BASE_HGB',
                'AUTO_TRADE_OVERLAP_CONFIRM': 'CONFIRM_R5_LIVE_TOP1',
            }

            output = io.StringIO()
            with (
                patch.dict(auto_trade.os.environ, env, clear=False),
                patch.object(auto_trade, 'Settings', return_value=fake_settings),
                patch.object(auto_trade, 'load_signal', signal_lookup),
                redirect_stdout(output),
            ):
                rc = asyncio.run(auto_trade.main_async())

            self.assertEqual(rc, 0)
            signal_lookup.assert_not_called()
            text = output.getvalue()
            self.assertIn('ENTRY_BLOCKED_PENDING_EXIT_PRIORITY', text)
            self.assertIn('MAX_HOLD_4_BUCKETS', text)
            self.assertIn('QCOM', text)

    def test_pending_exit_reason_is_persisted_and_priority_can_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ManagedPositionStore(pathlib.Path(tmp) / 'trading.sqlite3')
            ok, row = store.reserve_entry(
                run_id='run-qcom',
                symbol='QCOM',
                strategy_version='R5.1_BASE_HGB',
                signal_as_of='2026-09-25T14:30:00+00:00',
                client_order_id='order-qcom',
                target_exit_buckets=4,
            )
            self.assertTrue(ok)
            store.mark_open(
                row['position_id'],
                entry_status='FILLED',
                filled_quantity=Decimal('1'),
                average_price='200',
            )

            store.set_exit_pending(row['position_id'], 'MAX_HOLD_4_BUCKETS')
            first = store.get(row['position_id'])
            self.assertEqual(first['exit_pending_reason'], 'MAX_HOLD_4_BUCKETS')
            self.assertIsNotNone(first['exit_pending_since'])

            first_since = first['exit_pending_since']
            store.set_exit_pending(row['position_id'], 'STOP_LOSS_3PCT')
            upgraded = store.get(row['position_id'])
            self.assertEqual(upgraded['exit_pending_reason'], 'STOP_LOSS_3PCT')
            self.assertEqual(upgraded['exit_pending_since'], first_since)


if __name__ == '__main__':
    unittest.main()
