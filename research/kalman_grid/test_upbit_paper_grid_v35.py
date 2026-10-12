import unittest
from decimal import Decimal
from upbit_paper_grid_v35 import UpbitPaperGrid,evaluate_upbit
class TestV35(unittest.TestCase):
 def test_prices_tick_and_minimum(self):
  g=UpbitPaperGrid("3500555",spacing="0.14",cash="30000",notional="10000",fee="0.05")
  for oid in g.buys.values():
   o=g.ledger.orders[oid]
   self.assertEqual(o.price%Decimal("1000"),0)
   self.assertGreaterEqual(o.price*o.quantity,Decimal("5000"))
  g.ledger.audit()
 def test_buy_then_sell_has_valid_orders(self):
  g=UpbitPaperGrid("3500000",spacing="0.5",cash="30000",notional="10000",fee="0.05")
  entry=next(iter(g.buys.values()))
  px=g.ledger.orders[entry].price
  g.update(px,"entry")
  for sid in g.sells:
   o=g.ledger.orders[sid]
   self.assertEqual(o.price%Decimal("1000"),0)
   self.assertGreaterEqual(o.price*o.quantity,Decimal("5000"))
   g.update(o.price,"exit")
  g.ledger.audit()
 def test_recenter_preserves_lots_and_sells(self):
  g=UpbitPaperGrid("3500000",spacing="0.5",cash="30000",notional="10000",fee="0.05")
  g.update(g.ledger.orders[next(iter(g.buys.values()))].price,"entry")
  saved=set(g.sells);lots=set(g.ledger.lots)
  g.recenter("3600000")
  self.assertEqual(saved,set(g.sells))
  self.assertEqual(lots,set(g.ledger.lots))
  g.ledger.audit()
 def test_evaluate(self):
  r=evaluate_upbit([("0","3500000"),("1","3490000"),("2","3510000")],spacing="0.14")
  self.assertEqual(r["bars"],3)
  self.assertEqual(r["status"],"PAPER_CLOSE_ONLY_NO_SLIPPAGE")
 def test_slippage_block(self):
  with self.assertRaises(NotImplementedError):
   evaluate_upbit([("0","3500000")],slippage="0.02")
if __name__=="__main__":unittest.main()
