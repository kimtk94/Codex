from __future__ import annotations

import unittest
from datetime import datetime, timezone

from engine.r5_annual_ledger import (
    FORWARD_PROVENANCE,
    REPLAY_PROVENANCE,
    deterministic_trade_uuid,
    select_nonoverlap_signals,
)


class R5AnnualLedgerTests(unittest.TestCase):
    def test_nonoverlap_allows_entry_at_exact_previous_exit(self) -> None:
        signals = [
            {
                "timestamp": datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
                "expected_seq": 100,
                "expected_exit_seq": 104,
            },
            {
                "timestamp": datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc),
                "expected_seq": 101,
                "expected_exit_seq": 105,
            },
            {
                "timestamp": datetime(2026, 1, 2, 18, 30, tzinfo=timezone.utc),
                "expected_seq": 104,
                "expected_exit_seq": 108,
            },
            {
                "timestamp": datetime(2026, 1, 3, 15, 30, tzinfo=timezone.utc),
                "expected_seq": 107,
                "expected_exit_seq": 111,
            },
            {
                "timestamp": datetime(2026, 1, 3, 16, 30, tzinfo=timezone.utc),
                "expected_seq": 108,
                "expected_exit_seq": 112,
            },
        ]
        selected = select_nonoverlap_signals(signals)
        self.assertEqual(
            [x["expected_seq"] for x in selected],
            [100, 104, 108],
        )

    def test_trade_ids_separate_reconstructed_and_forward_provenance(self) -> None:
        original = "R5P_HGB_REFIT_R4|12345"
        replay_id = deterministic_trade_uuid(REPLAY_PROVENANCE, original)
        forward_id = deterministic_trade_uuid(FORWARD_PROVENANCE, original)
        self.assertNotEqual(replay_id, forward_id)
        self.assertEqual(
            replay_id,
            deterministic_trade_uuid(REPLAY_PROVENANCE, original),
        )

    def test_nonoverlap_is_stable_when_input_is_unsorted(self) -> None:
        signals = [
            {"timestamp": 3, "expected_seq": 14, "expected_exit_seq": 18},
            {"timestamp": 1, "expected_seq": 10, "expected_exit_seq": 14},
            {"timestamp": 2, "expected_seq": 12, "expected_exit_seq": 16},
        ]
        selected = select_nonoverlap_signals(signals)
        self.assertEqual([x["expected_seq"] for x in selected], [10, 14])


if __name__ == "__main__":
    unittest.main()
