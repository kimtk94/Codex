import unittest
from kalman_grid_v23 import Grid,simulate
class Test(unittest.TestCase):
 def test_buy_then_sell_and_refund(self):
  g=Grid('100',spacing='1',levels=10,cash='500',notional='100',exposure_cap='500')
  g.update('98','t1');self.assertGreater(g.ledger.asset,0)
  g.update('100','t2');self.assertGreater(g.ledger.realized,0)
  self.assertTrue(g.ledger.audit())
 def test_bounded_cash(self):
  g=Grid('100',spacing='.14',levels=100,cash='30000',notional='10000',exposure_cap='30000')
  self.assertLessEqual(len(g.buys),3)
  for i in range(1,40):g.update(str(100-i/10),str(i));self.assertGreaterEqual(g.ledger.free,0)
 def test_no_instant_buy_sell(self):
  g=Grid('100',spacing='1',levels=6,cash='500',notional='100')
  g.update('90');self.assertEqual(len([x for x in g.fills if x['side']=='SELL']),0)
 def test_stable_series(self):
  g,p,n=simulate([(str(i),'100') for i in range(50)])
  self.assertEqual(len(g.fills),0);self.assertEqual(n,50)
 def test_invalid(self):
  with self.assertRaises(ValueError):Grid('100',spacing='0')
if __name__=='__main__':unittest.main()
