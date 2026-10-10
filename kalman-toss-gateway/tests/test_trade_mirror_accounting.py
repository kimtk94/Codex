"""No broker, secrets, or database needed: regression tests for LIVE mirror math."""
import json
import unittest
from decimal import Decimal

from engine.trade_mirror_accounting import (
    broker_reconciled_status, link_position_orders, position_round_trip,
)


def order(cid, symbol, side, time, qty, price, *, entry_type="", tax="0", commission="0"):
    return {
        "client_order_id": cid, "symbol": symbol, "side": side, "created_at": time,
        "status": "SUBMITTED",
        "telemetry_json": json.dumps({
            "signal_context": {"entry_type": entry_type, "strategy_version": "R5.1_BASE_HGB"},
            "broker_order": {
                "status": "FILLED", "filled_quantity": str(qty),
                "average_filled_price": str(price), "commission": str(commission),
                "tax": str(tax), "currency": "USD",
            },
        }),
    }


class TestPositionAccounting(unittest.TestCase):
    def setUp(self):
        self.p = {
            "position_id": "pos-abc", "symbol": "AMD", "strategy_version": "R5.1_BASE_HGB",
            "state": "CLOSED", "created_at": "2026-09-22T14:00:00+00:00",
            "updated_at": "2026-09-22T17:00:00+00:00",
            "entry_client_order_id": "buy-a", "exit_client_order_id": "sell-a",
            "entry_count": 2, "entry_filled_quantity": "0.02",
            "remaining_quantity": "0", "entry_avg_fill_price": "101",
        }
        self.orders = [
            order("buy-a", "AMD", "BUY", "2026-09-22T14:00:01+00:00", ".01", "100"),
            order("buy-b", "AMD", "BUY", "2026-09-22T15:00:00+00:00", ".01", "102", entry_type="ADD_ON"),
            order("sell-a", "AMD", "SELL", "2026-09-22T16:00:00+00:00", ".02", "100", tax=".01"),
        ]

    def matched(self, positions=None, orders=None):
        positions = self.p if positions is None else positions
        orders = self.orders if orders is None else orders
        links = link_position_orders([positions], orders)
        return [(o, links[o["client_order_id"]][1]) for o in orders if o["client_order_id"] in links]

    def test_add_on_fill_must_not_double_return(self):
        links = link_position_orders([self.p], self.orders)
        self.assertEqual(links["buy-b"][1], "ADD_ON")
        result = position_round_trip(self.p, self.matched())
        self.assertEqual(result["audit_status"], "PASS")
        self.assertAlmostEqual(result["gross_return"], 2 / 2.02 - 1)
        self.assertAlmostEqual(result["net_return"], 1.99 / 2.02 - 1)
        self.assertEqual(result["entry_leg_count"], 2)

    def test_missing_add_on_blocks_net_pnl(self):
        result = position_round_trip(self.p, self.matched(orders=self.orders[::2]))
        self.assertEqual(result["audit_status"], "INCOMPLETE")
        self.assertNotIn("net_return", result)

    def test_order_fill_mismatch_blocks_net_pnl(self):
        p = dict(self.p, entry_filled_quantity=".03")
        result = position_round_trip(p, self.matched(positions=p))
        self.assertEqual(result["reason"], "FILL_QUANTITY_MISMATCH")
        self.assertNotIn("net_return", result)

    def test_stale_submitted_reconciled_only_on_broker_fill(self):
        self.assertEqual(broker_reconciled_status(self.orders[1]), ("FILLED", "broker_fill_telemetry"))
        incomplete = {"status": "SUBMITTED", "telemetry_json": json.dumps({
            "broker_order": {"status": "SUBMITTED", "filled_quantity": "0"}
        })}
        self.assertEqual(broker_reconciled_status(incomplete), ("SUBMITTED", "order_guard"))

    def test_add_on_not_linked_to_later_reentry(self):
        later = dict(self.p, position_id="pos-next", created_at="2026-09-23T13:00:00+00:00",
                     updated_at="2026-09-23T18:00:00+00:00")
        links = link_position_orders([self.p, later], self.orders)
        self.assertEqual(links["buy-b"][0]["position_id"], "pos-abc")

    def test_incomplete_adopted_position_cannot_invent_fees(self):
        p = dict(self.p, entry_count=1, entry_client_order_id="adopted-amd")
        result = position_round_trip(p, [(self.orders[2], "EXIT")])
        self.assertEqual(result["audit_status"], "INCOMPLETE")
        self.assertNotIn("net_return", result)

    def test_real_world_multi_add_on_case(self):
        p = dict(self.p, symbol="INTC", entry_count=3,
                 entry_filled_quantity=".095067", entry_avg_fill_price="115.59449251580465")
        orders = [
            order("buy-a", "INTC", "BUY", "2026-09-22T14:00:01+00:00", ".031702", "115.44"),
            order("buy-b", "INTC", "BUY", "2026-09-22T15:00:00+00:00", ".031829", "114.98", entry_type="ADD_ON"),
            order("buy-c", "INTC", "BUY", "2026-09-22T15:30:00+00:00", ".031536", "116.37", entry_type="ADD_ON"),
            order("sell-a", "INTC", "SELL", "2026-09-22T16:00:00+00:00", ".095067", "115.35", tax=".01", commission=".01"),
        ]
        matched = self.matched(positions=p, orders=orders)
        result = position_round_trip(p, matched)
        self.assertEqual(result["audit_status"], "PASS")
        self.assertLess(result["net_return"], 0)
        self.assertGreater(result["net_return"], -.01)
        self.assertAlmostEqual(result["position_cost_basis_difference_bps"], 0, places=6)
        self.assertNotAlmostEqual(result["net_return"], 1.986969475, places=2)


if __name__ == "__main__":
    unittest.main()
