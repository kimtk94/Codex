import unittest
from decimal import Decimal as D
from order_ledger import Ledger,State
class Tests(unittest.TestCase):
 def test_partial_buy_cancel(self):
  x=Ledger(30000);a=x.place('BUY','100','100');self.assertEqual(x.locked,D('10004.0000'))
  x.fill(a,'25');self.assertEqual(x.orders[a].state,State.PARTIAL)
  self.assertEqual(x.locked,D('7503.0000'));x.cancel(a);self.assertEqual(x.locked,0);x.audit()
 def test_sell_partial_and_reentry(self):
  x=Ledger(30000);a=x.place('BUY','100','100');x.fill(a,'100');lot=next(iter(x.lots))
  s=x.place('SELL','101','100',a);x.fill(s,'40',lot_id=lot);self.assertEqual(x.sell_locked,D(60))
  x.fill(s,'60',lot_id=lot);self.assertEqual(x.asset,0);self.assertGreater(x.realized,0)
  x.place('BUY','100','100',s);x.audit()
 def test_price_improvement(self):
  x=Ledger(1000);a=x.place('BUY','10','40');x.fill(a,'40','9');self.assertEqual(x.free,x.cash);x.audit()
 def test_invalid_limit_and_double_fill(self):
  x=Ledger(1000);a=x.place('BUY','10','40')
  with self.assertRaises(ValueError):x.fill(a,40,11)
  x.fill(a,40)
  with self.assertRaises(ValueError):x.fill(a,1)
 def test_sell_inventory_double_reserve(self):
  x=Ledger(1000);a=x.place('BUY','10','40');x.fill(a,40);x.place('SELL','11',30)
  with self.assertRaises(ValueError):x.place('SELL','12',20)
 def test_cancel_replace(self):
  x=Ledger(1000);a=x.place('BUY','10','40');b=x.replace(a,'9','30')
  self.assertEqual(x.orders[a].state,State.CANCELLED);self.assertEqual(x.orders[b].state,State.OPEN);x.audit()
 def test_exposure(self):
  x=Ledger(1000,exposure_cap=400);x.place('BUY','10',30)
  with self.assertRaises(ValueError):x.place('BUY','10',20)
 def test_minimum(self):
  x=Ledger(1000,min_notional=50)
  with self.assertRaises(ValueError):x.place('BUY',10,4)
 def test_100_order_reservation(self):
  x=Ledger(600000);ids=[x.place('BUY',100,i+1) for i in range(100)]
  self.assertEqual(len(ids),100);x.audit()
 def test_fee_conservation(self):
  x=Ledger('30000',fee_pct='0.05');a=x.place('BUY',100,100);x.fill(a,100);k=next(iter(x.lots));b=x.place('SELL',101,100);x.fill(b,100,lot_id=k)
  self.assertEqual(x.cash,D(30000)+x.realized);x.audit()
if __name__=='__main__':unittest.main(verbosity=2)
