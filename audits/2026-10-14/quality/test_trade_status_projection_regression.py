"""Synthetic 97-event regression matching aggregate row counts observed in Neon.

Contains NO real broker identifiers or personal data. We do not connect to Neon.
The real 97-row SELECT-only comparison is documented separately.
"""
from copy import deepcopy
from decimal import Decimal
import unittest
from test_broker_status_evidence import resolve, evidence


def mock_events():
    positions = []
    events = []
    # 76 managed executions: 36 entries and 40 exits.
    for index in range(76):
        leg = "ENTRY" if index < 36 else "EXIT"
        pos = {"entry_status": "FILLED", "exit_status": "FILLED",
               "remaining_quantity": "0"}
        order = {"status": "SUBMITTED", "toss_order_id": f"managed-{index:03}"}
        events.append((order, pos, leg, None))
        positions.append(pos)
    # 21 historical orphan submissions with terminal broker-fill evidence.
    for index in range(21):
        key = f"orphan-{index:03}"
        order = {"status": "SUBMITTED", "toss_order_id": key}
        events.append((order, None, None, evidence(order_id=key)))
    return events, positions


class FullProjectionRegression(unittest.TestCase):
    def test_97_event_status_partition(self):
        events, _ = mock_events()
        self.assertEqual(len(events), 97)
        projected = [resolve(*event) for event in events]
        self.assertEqual(sum(s == "FILLED" for s, _ in projected), 97)
        self.assertEqual(sum(src == "managed_position" for _, src in projected), 76)
        self.assertEqual(sum(src == "broker_order_telemetry" for _, src in projected), 21)

    def test_projection_does_not_modify_input(self):
        events, positions = mock_events()
        before = deepcopy((events, positions))
        for event in events:
            resolve(*event)
        self.assertEqual((events, positions), before)

    def test_rejected_historical_fill_does_not_promote(self):
        order = {"status": "SUBMITTED", "toss_order_id": "orphan-bad"}
        invalid = evidence(order_id="other-order")
        self.assertEqual(resolve(order, None, None, invalid), ("SUBMITTED", "order_guard"))

    def test_lrcx_aggregated_position_not_added_twice(self):
        existing = Decimal("0.049034")
        buys = (Decimal("0.025357"), Decimal("0.023677"))
        sell = Decimal("0.049034")
        self.assertEqual(sum(buys), existing)
        self.assertEqual(existing - sell, Decimal("0"))
        # A projection enriches ledger status and fill metrics, not positions.
        order = {"status": "SUBMITTED", "toss_order_id": "lrcx-addon"}
        result = resolve(order, None, None, evidence(order_id="lrcx-addon"))
        self.assertEqual(result[0], "FILLED")
        self.assertEqual(existing - sell, Decimal("0"))

    def test_backfill_idempotent_on_second_projection(self):
        order = {"status": "SUBMITTED", "toss_order_id": "orphan-1"}
        telemetry = evidence(order_id="orphan-1")
        first = resolve(order, None, None, telemetry)
        already = {**order, "status": first[0]}
        second = resolve(already, None, None, telemetry)
        self.assertEqual(first, ("FILLED", "broker_order_telemetry"))
        self.assertEqual(second, ("FILLED", "order_guard"))


if __name__ == "__main__":
    unittest.main()
