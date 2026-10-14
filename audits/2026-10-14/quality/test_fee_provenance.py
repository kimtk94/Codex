"""Offline fee-evidence regression; never uses live trading or broker I/O."""
import ast
from decimal import Decimal
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
SOURCE=(ROOT/"kalman-toss-gateway"/"engine"/"trade_mirror.py").read_text(encoding="utf-8")
tree=ast.parse(SOURCE)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)
       and n.name in {"_dec","_execution_quality","_round_trip_quality"}]
ns={"Decimal":Decimal}
exec(compile(ast.Module(body=nodes,type_ignores=[]),"<audit-fee>", "exec"),ns)
quality=ns["_execution_quality"]
net=ns["_round_trip_quality"]

def broker(commission="0",tax="0",fee_currency="USD",ccy="USD",qty="0.1",px="100"):
    data={"filled_quantity":qty,"average_filled_price":px,
          "commission":commission,"tax":tax,"currency":ccy,
          "fee_currency":fee_currency,"status":"FILLED"}
    return {"broker_order":data}

def position():
    return {"state":"CLOSED","entry_filled_quantity":"0.1",
            "remaining_quantity":"0","entry_avg_fill_price":"100",
            "exit_avg_fill_price":"101"}

def inputs():
    return quality("BUY",None,broker()),quality("SELL",None,broker(px="101"))

class FeeEvidenceTests(unittest.TestCase):
    def test_zero_reported_fees_remain_valid_zero(self):
        x,y=inputs()
        self.assertEqual(x["commission"],0)
        self.assertEqual(x["tax"],0)
        self.assertEqual(x["cost_bps"],0)
        self.assertEqual(net(x,y,position=position())["quality_status"],"FULL_LEG_COVERAGE")

    def test_missing_commission_not_zero(self):
        x,y=inputs()
        del_fee=broker()
        del del_fee["broker_order"]["commission"]
        x=quality("BUY",None,del_fee)
        self.assertIsNone(x["commission"])
        self.assertIsNone(x["cost_bps"])
        self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_FEE_EVIDENCE")
        self.assertIsNone(net(x,y,position=position())["net_return"])

    def test_missing_tax_not_zero(self):
        x,y=inputs()
        data=broker()
        del data["broker_order"]["tax"]
        y=quality("SELL",None,data)
        self.assertIsNone(y["tax"])
        self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_FEE_EVIDENCE")

    def test_explicit_fee_absence_without_broker_payload(self):
        x,y=inputs()
        x=quality("BUY",None,{})
        self.assertIsNone(x["tax"])
        self.assertIsNone(x["commission"])
        # A completely absent broker payload fails earlier on fill-quantity
        # coverage. That is more specific and should not be downgraded.
        self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_LEG_COVERAGE")

    def test_negative_fee_is_unverified(self):
        x,y=inputs()
        x=quality("BUY",None,broker(commission="-0.01"))
        self.assertIsNone(x["commission"])
        self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_FEE_EVIDENCE")

    def test_nonfinite_fee_unverified(self):
        for val in ("NaN","Infinity","-Infinity"):
            with self.subTest(val=val):
                x,y=inputs()
                x=quality("BUY",None,broker(tax=val))
                self.assertIsNone(x["tax"])
                self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_FEE_EVIDENCE")

    def test_fee_currency_missing_unverified(self):
        x,y=inputs()
        x=quality("BUY",None,broker(fee_currency=None))
        r=net(x,y,position=position())
        self.assertEqual(r["quality_status"],"UNVERIFIED_FEE_CURRENCY")
        self.assertIsNone(r["net_return"])

    def test_fee_in_krw_while_fill_usd_unverified(self):
        x,y=inputs()
        y=quality("SELL",None,broker(px="101",fee_currency="KRW"))
        self.assertEqual(net(x,y,position=position())["quality_status"],"UNVERIFIED_FEE_CURRENCY")

    def test_quote_currency_alone_is_not_provenance(self):
        x,y=inputs()
        d=broker(ccy=None)
        d["pretrade_quote"]={"currency":"USD"}
        x=quality("BUY",None,d)
        self.assertEqual(x["currency"],"USD")
        self.assertIsNone(x["broker_currency"])
        self.assertEqual(net(x,y,position=position())["quality_status"],"UNVERIFIED_FEE_CURRENCY")

    def test_positive_commission_changes_net(self):
        base_entry,base_exit=inputs()
        fee_entry=quality("BUY",None,broker(commission="0.01"))
        fee_exit=quality("SELL",None,broker(commission="0.01",px="101"))
        orig=net(base_entry,base_exit,position=position())
        cost=net(fee_entry,fee_exit,position=position())
        self.assertLess(cost["net_return"],orig["net_return"])
        self.assertGreater(cost["round_trip_cost_bps"],0)

    def test_coverage_precedes_fee_completeness(self):
        x,y=inputs()
        x["filled_quantity"]=0.05
        x["commission"]=None
        self.assertEqual(net(x,y,position=position())["quality_status"],"INCOMPLETE_LEG_COVERAGE")

    def test_no_unverified_fee_net_return(self):
        x,y=inputs()
        y["commission"]=None
        r=net(x,y,position=position())
        self.assertIsNone(r["net_return_pct"])
        self.assertIsNone(r["round_trip_cost_bps"])

    def test_source_contains_no_missing_fee_zero_coercion(self):
        self.assertNotIn('_dec(broker.get("commission")) or Decimal("0")',SOURCE)
        self.assertNotIn('_dec(broker.get("tax")) or Decimal("0")',SOURCE)

if __name__=="__main__":
    unittest.main()
