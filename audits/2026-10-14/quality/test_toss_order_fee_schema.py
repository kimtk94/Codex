"""Mock response-contract tests: NO actual account/order data or I/O."""
import ast
import unittest
from pathlib import Path
from toss_order_fee_schema import ORDER_EXECUTION_FIELDS, check_fee_schema

ROOT = Path(__file__).resolve().parents[3]
POSITION_MANAGER = ROOT / "kalman-toss-gateway" / "engine" / "position_manager.py"
MIRROR = ROOT / "kalman-toss-gateway" / "engine" / "trade_mirror.py"


def example_order(commission="0", tax="0"):
    return {"orderId": "REDACTED", "symbol": "SYNTHETIC",
            "currency": "USD", "status": "FILLED",
            "execution": {"filledQuantity": "0.1",
                          "averageFilledPrice": "100",
                          "filledAmount": "10",
                          "commission": commission, "tax": tax,
                          "filledAt": "2026-10-14T00:00:00Z"}}


class SchemaTests(unittest.TestCase):
    def test_documented_fields_only(self):
        self.assertEqual(ORDER_EXECUTION_FIELDS,
                         {"filledQuantity","averageFilledPrice","filledAmount",
                          "commission","tax","filledAt","settlementDate"})
        self.assertNotIn("feeCurrency", ORDER_EXECUTION_FIELDS)

    def test_reported_zero_fee_still_currency_unverified(self):
        d = check_fee_schema(example_order())
        self.assertEqual(d["status"], "FEE_AMOUNT_FIELDS_PRESENT_CURRENCY_UNVERIFIED")
        self.assertFalse(d["net_pnl_eligible"])

    def test_nonzero_fee_still_currency_unverified(self):
        d = check_fee_schema(example_order("0.01","0.02"))
        self.assertEqual(d["status"], "FEE_AMOUNT_FIELDS_PRESENT_CURRENCY_UNVERIFIED")
        self.assertFalse(d["net_pnl_eligible"])

    def test_no_values_or_ids_leak_to_report(self):
        d = check_fee_schema(example_order("9876.54","1"))
        self.assertNotIn("9876.54", repr(d))
        self.assertNotIn("REDACTED", repr(d))

    def test_missing_fee_never_becomes_zero(self):
        for key in ("commission","tax"):
            with self.subTest(key=key):
                r = example_order()
                del r["execution"][key]
                self.assertFalse(check_fee_schema(r)["net_pnl_eligible"])
                self.assertTrue(check_fee_schema(r)["reason"].startswith("MISSING_OR_INVALID_"))

    def test_invalid_numbers(self):
        for v in ("NaN","Infinity","-1",True,1.0):
            with self.subTest(value=v):
                self.assertFalse(check_fee_schema(example_order(commission=v))["net_pnl_eligible"])

    def test_unwrapped_order_only(self):
        self.assertEqual(check_fee_schema({"result":example_order()})["reason"],
                         "UNWRAP_RESPONSE_BEFORE_VALIDATION")

    def test_no_assumed_currency(self):
        r = example_order()
        r.pop("currency")
        self.assertEqual(check_fee_schema(r)["reason"],"TRADE_CURRENCY_UNVERIFIED")

    def test_missing_execution_fails(self):
        r=example_order()
        r.pop("execution")
        self.assertEqual(check_fee_schema(r)["reason"],"ORDER_EXECUTION_MISSING")

    def test_partial_order_cannot_claim_complete_fees(self):
        r=example_order()
        r["execution"]["filledQuantity"]="0"
        self.assertEqual(check_fee_schema(r)["reason"],"NO_POSITIVE_FILL")

    def test_position_manager_stores_parent_currency_but_not_fee_currency(self):
        src=POSITION_MANAGER.read_text(encoding="utf-8")
        tree=ast.parse(src)
        fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_broker_order_telemetry")
        code=ast.get_source_segment(src,fun)
        self.assertIn("'currency': order.get('currency')",code)
        self.assertIn("'commission': execution.get('commission')",code)
        self.assertIn("'tax': execution.get('tax')",code)
        self.assertNotIn("'fee_currency':",code)

    def test_mirror_does_not_infer_fee_currency_from_quote(self):
        src=MIRROR.read_text(encoding="utf-8")
        tree=ast.parse(src)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_execution_quality")
        code=ast.get_source_segment(src,fn)
        self.assertIn('broker.get("fee_currency")',code)
        self.assertNotIn('broker.get("fee_currency") or broker.get("currency")',code)


if __name__=="__main__":
    unittest.main()
