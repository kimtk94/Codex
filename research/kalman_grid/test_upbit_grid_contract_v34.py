import unittest
from decimal import Decimal as D
from upbit_grid_contract_v34 import paper_limit_order,roundtrip_at_ticks
class TestPaperContract(unittest.TestCase):
 def test_directional_rounding(self):
  self.assertEqual(paper_limit_order("BUY","3500555","0.003")["price"],"3500000")
  self.assertEqual(paper_limit_order("SELL","3500555","0.003")["price"],"3501000")
 def test_minimum_after_rounding(self):
  with self.assertRaises(ValueError):paper_limit_order("BUY","3500555","0.001")
 def test_tick_roundtrip_vs_nominal_margin(self):
  r=roundtrip_at_ticks("3500555","3505456","0.003",fee_pct="0.05")
  self.assertEqual(r["buy"]["price"],"3500000")
  self.assertEqual(r["sell"]["price"],"3506000")
  self.assertGreater(D(r["net_profit_krw"]),0)
 def test_slippage_erases_margin(self):
  r=roundtrip_at_ticks("3500555","3505456","0.003",fee_pct="0.05",slippage_pct="0.1")
  self.assertLess(D(r["net_profit_krw"]),0)
if __name__=="__main__":unittest.main()
