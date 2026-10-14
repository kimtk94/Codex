"""Offline tests for the audit-branch fail-closed net-return calculation.

No production imports, credentials, network, database, or trading side effects.
"""
import ast
from decimal import Decimal
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "kalman-toss-gateway" / "engine" / "trade_mirror.py"
SOURCE = FILE.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCS = [x for x in TREE.body if isinstance(x, ast.FunctionDef)
         and x.name in {"_dec", "_round_trip_quality"}]
ns = {"Decimal": Decimal}
exec(compile(ast.Module(body=FUNCS, type_ignores=[]), str(FILE), "exec"), ns)
round_trip = ns["_round_trip_quality"]


def position(total="0.049034", remaining="0", entry_price="295.9079954725292654",
             exit_price="290.91", state="CLOSED"):
    return {"entry_filled_quantity": total, "remaining_quantity": remaining,
            "entry_avg_fill_price": entry_price, "exit_avg_fill_price": exit_price,
            "state": state}


def quality(qty, price, fee="0.01"):
    q = Decimal(qty)
    p = Decimal(price)
    return {"filled_quantity": float(q), "exact_notional": float(q * p),
            "commission": float(Decimal(fee)), "tax": 0.0,
            "broker_currency": "USD", "fee_currency": "USD"}


class NetReturnCoverage(unittest.TestCase):
    def setUp(self):
        self.entry = quality("0.025357", "295.9079954725292654")
        self.exit = quality("0.049034", "290.91")

    def test_lrcx_add_on_net_is_unavailable(self):
        result = round_trip(self.entry, self.exit, position=position())
        self.assertEqual(result["quality_status"], "INCOMPLETE_LEG_COVERAGE")
        self.assertIsNone(result["net_return"])
        self.assertIsNone(result["round_trip_cost_bps"])

    def test_lrcx_gross_remains_negative(self):
        result = round_trip(self.entry, self.exit, position=position())
        self.assertAlmostEqual(result["gross_return_pct"], -1.68903698, places=5)

    def test_complete_single_entry_returns_reasonable_net(self):
        entry = quality("0.049034", "295.9079954725292654")
        result = round_trip(entry, self.exit, position=position())
        self.assertEqual(result["quality_status"], "FULL_LEG_COVERAGE")
        self.assertLess(result["net_return"], 0)
        self.assertGreater(result["net_return"], -0.1)

    def test_missing_entry_fill_qty_fails_closed(self):
        entry = {**self.entry, "filled_quantity": None}
        self.assertIsNone(round_trip(entry, self.exit, position=position())["net_return"])

    def test_missing_exit_fill_qty_fails_closed(self):
        ex = {**self.exit, "filled_quantity": None}
        self.assertIsNone(round_trip(self.entry, ex, position=position())["net_return"])

    def test_open_position_fails_closed(self):
        self.assertEqual(round_trip(self.entry, self.exit, position=position(state="OPEN"))["quality_status"],
                         "POSITION_NOT_CLOSED")

    def test_partial_exit_fails_closed(self):
        result = round_trip(self.entry, self.exit,
                            position=position(remaining="0.023677", state="CLOSED"))
        self.assertIsNone(result["net_return"])

    def test_small_quantity_rounding_allowed(self):
        e = quality("0.049034000001", "295.9079954725292654")
        result = round_trip(e, self.exit, position=position())
        self.assertEqual(result["quality_status"], "FULL_LEG_COVERAGE")

    def test_main_callsite_passes_full_position(self):
        self.assertIn("_round_trip_quality(entry_quality, exit_quality, position=p)", SOURCE)

    def test_add_on_does_not_change_aggregate_position(self):
        before = position()
        _ = round_trip(self.entry, self.exit, position=before)
        self.assertEqual(before["entry_filled_quantity"], "0.049034")
        self.assertEqual(before["remaining_quantity"], "0")


if __name__ == "__main__":
    unittest.main()
