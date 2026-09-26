from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.managed_positions import ManagedPositionStore
from engine import auto_trade


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

    def test_2335_r5_entry_can_finish_before_fractional_close(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_SAFE_EXIT_WINDOW_ENABLED': 'true',
                'AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            allowed, detail = auto_trade._entry_exit_window_check(
                self._window(),
                anchor_signal_as_of='2026-09-25T13:30:00+00:00',
                strategy_version='R5.1_BASE_HGB',
                target_exit_buckets=4,
            )

        self.assertTrue(allowed)
        self.assertEqual(detail['reason'], 'SAFE')
        self.assertEqual(
            detail['projectedMaxHoldExitAt'],
            '2026-09-25T18:30:00+00:00',
        )
        self.assertEqual(
            detail['safeExitDeadlineAt'],
            '2026-09-26T03:45:00+09:00',
        )

    def test_0035_r5_initial_entry_is_blocked_as_too_late(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_SAFE_EXIT_WINDOW_ENABLED': 'true',
                'AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            allowed, detail = auto_trade._entry_exit_window_check(
                self._window(),
                anchor_signal_as_of='2026-09-25T14:30:00+00:00',
                strategy_version='R5.1_BASE_HGB',
                target_exit_buckets=4,
            )

        self.assertFalse(allowed)
        self.assertEqual(
            detail['reason'],
            'PROJECTED_EXIT_AFTER_SAFE_DEADLINE',
        )
        self.assertEqual(
            detail['projectedMaxHoldExitAt'],
            '2026-09-25T19:30:00+00:00',
        )

    def test_add_on_can_use_original_position_exit_clock(self):
        with patch.dict(
            auto_trade.os.environ,
            {
                'AUTO_TRADE_SAFE_EXIT_WINDOW_ENABLED': 'true',
                'AUTO_TRADE_EXIT_WINDOW_BUFFER_MINUTES': '15',
                'AUTO_TRADE_SIGNAL_BAR_MINUTES': '60',
            },
            clear=False,
        ):
            allowed, _ = auto_trade._entry_exit_window_check(
                self._window(),
                anchor_signal_as_of='2026-09-25T13:30:00+00:00',
                strategy_version='R5.1_BASE_HGB',
                target_exit_buckets=4,
            )

        self.assertTrue(allowed)

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
