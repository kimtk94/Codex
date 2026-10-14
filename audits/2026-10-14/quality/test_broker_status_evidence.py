"""Tests for strict telemetry fallback in the audit-only trade_mirror.py patch."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "kalman-toss-gateway"))
from engine.broker_status_evidence import historical_broker_fill

mirror_file = ROOT / "kalman-toss-gateway" / "engine" / "trade_mirror.py"
mirror_source = mirror_file.read_text(encoding="utf-8")
tree = ast.parse(mirror_source)
node = next(item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "_execution_status")
namespace = {"historical_broker_fill": historical_broker_fill}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(mirror_file), "exec"), namespace)
resolve = namespace["_execution_status"]


def evidence(status="FILLED", order_id="broker-01", quantity="0.023677",
             code=200, filled_at="2026-10-14T01:39:16+09:00"):
    return {"broker_order": {
        "order_id": order_id, "status": status, "filled_quantity": quantity,
        "average_filled_price": "299.44", "filled_at": filled_at,
        "response_meta": {"status_code": code},
    }}


class EvidenceFallbackTests(unittest.TestCase):
    def setUp(self):
        self.order = {"status": "SUBMITTED", "toss_order_id": "broker-01"}

    def test_historical_filled_orphan(self):
        self.assertEqual(resolve(self.order, None, None, evidence()),
                         ("FILLED", "broker_order_telemetry"))

    def test_evidence_quantity(self):
        fill = historical_broker_fill(self.order, evidence())
        self.assertEqual(str(fill["filled_quantity"]), "0.023677")
        self.assertEqual(str(fill["average_filled_price"]), "299.44")

    def test_broker_order_id_mismatch_fails_closed(self):
        self.assertEqual(resolve(self.order, None, None, evidence(order_id="wrong")),
                         ("SUBMITTED", "order_guard"))

    def test_broker_not_filled(self):
        self.assertEqual(resolve(self.order, None, None, evidence(status="SUBMITTED")),
                         ("SUBMITTED", "order_guard"))

    def test_missing_http_200(self):
        self.assertEqual(resolve(self.order, None, None, evidence(code=401)),
                         ("SUBMITTED", "order_guard"))

    def test_invalid_quantity(self):
        for q in ("0", "NaN", "-1", "Infinity"):
            with self.subTest(q=q):
                self.assertIsNone(historical_broker_fill(self.order, evidence(quantity=q)))

    def test_unparseable_fill_time(self):
        self.assertIsNone(historical_broker_fill(self.order, evidence(filled_at="bad")))

    def test_managed_status_still_preferred(self):
        self.assertEqual(resolve(self.order, {"entry_status": "CANCELED"}, "ENTRY",
                                 evidence()), ("CANCELED", "managed_position"))

    def test_no_telemetry_preserves_guard(self):
        self.assertEqual(resolve(self.order, None, None), ("SUBMITTED", "order_guard"))

    def test_callsite_persists_broker_quantity_and_provenance(self):
        self.assertIn("_execution_status(o, pos, leg, telemetry)", mirror_source)
        self.assertIn('filled = broker_fill["filled_quantity"]', mirror_source)
        self.assertIn('avg = broker_fill["average_filled_price"]', mirror_source)


if __name__ == "__main__":
    unittest.main()
