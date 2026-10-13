import unittest
from upbit_v45_depth_sweep import DepthGrid,one

class TestDepthFunding(unittest.TestCase):
 def test_exact_buy_depth(self):
  g=DepthGrid("3500000",depth=100,spacing="0.18",cash="1000000",notional="5500",fee="0.05",exposure_cap="1000000")
  self.assertEqual(len(g.buy_levels),100)
  self.assertEqual(len(g.buys),100)
  self.assertGreater(g.ledger.locked,0)
  g.ledger.audit()
 def test_unaffordable_depth_explicitly_blocked(self):
  obs=[("2026-08-01T00:00:00+00:00","3500000"),("2026-08-01T00:01:00+00:00","3500000")]
  for depth in (200,300):
   result=one(obs,"2026-08","KRW-ETH","0.18",depth,"1000000","5500","0.05")
   self.assertEqual(result["status"],"BLOCKED_INSUFFICIENT_CAPITAL")
   self.assertLess(result["initial_funded_buys"],depth)
 def test_shallow_depth_completes(self):
  obs=[("2026-08-01T00:00:00+00:00","3500000"),("2026-08-01T00:01:00+00:00","3500000")]
  r=one(obs,"2026-08","KRW-ETH","0.18",50,"1000000","5500","0.05")
  self.assertEqual(r["status"],"PAPER_COMPLETE")
  self.assertEqual(r["initial_funded_buys"],50)
  self.assertEqual(r["fills"],0)

if __name__=="__main__":unittest.main()
