import ast
import unittest
from pathlib import Path
from position_link_contract import classify_local_position_link as link

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "kalman-toss-gateway" / "engine" / "auto_trade.py"


class LocalPositionAttributionTests(unittest.TestCase):
    def setUp(self):
        self.positions = [{"position_id": "pos-demo", "symbol": "LRCX",
                           "entry_run_id": "run-init"}]
        self.order = {
            "side": "BUY", "symbol": "LRCX",
            "signal_context": {
                "managed_position_id": "pos-demo", "symbol": "LRCX",
                "run_id": "run-add", "entry_type": "ADD_ON",
                "entry_count_before": 1,
            },
        }

    def test_explicit_add_on_link(self):
        result = link(self.order, self.positions)
        self.assertEqual(result["status"], "EXPLICIT_LOCAL_LINK")
        self.assertEqual(result["leg"], "ADD_ON")
        self.assertFalse(result["broker_confirmed"])

    def test_no_position_id_never_guesses_from_symbol_or_time(self):
        context = {**self.order["signal_context"]}
        del context["managed_position_id"]
        order = {**self.order, "signal_context": context,
                 "created_at": "2026-10-14T01:39:00+09:00"}
        self.assertEqual(link(order, self.positions)["reason"], "EXPLICIT_POSITION_ID_MISSING")

    def test_duplicate_id_fails(self):
        self.assertEqual(link(self.order, self.positions * 2)["status"], "UNKNOWN")

    def test_symbol_mismatch_fails(self):
        other = [{**self.positions[0], "symbol": "AMD"}]
        self.assertEqual(link(self.order, other)["reason"], "POSITION_SYMBOL_MISMATCH")

    def test_wrong_context_symbol_fails(self):
        order = {**self.order, "signal_context": {**self.order["signal_context"], "symbol": "AMD"}}
        self.assertEqual(link(order, self.positions)["status"], "UNKNOWN")

    def test_missing_record_fails(self):
        self.assertEqual(link(self.order, [])["status"], "UNKNOWN")

    def test_invalid_add_on_ordinal_fails(self):
        order = {**self.order, "signal_context": {**self.order["signal_context"], "entry_count_before": True}}
        self.assertEqual(link(order, self.positions)["status"], "UNKNOWN")

    def test_sell_not_inferred_from_buy_context(self):
        self.assertEqual(link({**self.order, "side": "SELL"}, self.positions)["status"], "UNKNOWN")

    def test_initial_run_must_match(self):
        ctx = {**self.order["signal_context"], "entry_type": "INITIAL"}
        self.assertEqual(link({**self.order, "signal_context": ctx}, self.positions)["status"], "UNKNOWN")
        ctx["run_id"] = "run-init"
        self.assertEqual(link({**self.order, "signal_context": ctx}, self.positions)["status"], "EXPLICIT_LOCAL_LINK")

    def test_source_persists_id_under_signal_context(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        candidates = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [x.value if isinstance(x, ast.Constant) else None for x in node.keys]
                if "entry_type" in keys and "managed_position_id" in keys:
                    candidates.append(node)
        self.assertEqual(len(candidates), 1)
        node = candidates[0]
        mapping = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        value = mapping["managed_position_id"]
        self.assertIsInstance(value, ast.Subscript)
        self.assertIsInstance(value.value, ast.Name)
        self.assertEqual(value.value.id, "position")
        self.assertIsInstance(value.slice, ast.Constant)
        self.assertEqual(value.slice.value, "position_id")


if __name__ == "__main__":
    unittest.main()
