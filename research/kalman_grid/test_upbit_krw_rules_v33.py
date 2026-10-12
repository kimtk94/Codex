import unittest
from decimal import Decimal
from upbit_krw_rules_v33 import price_tick,snap_price,validate_order,roundtrip_margin
class TestUpbitRules(unittest.TestCase):
 def test_btc_eth_tick(self):
  self.assertEqual(price_tick("110000000"),Decimal("1000"))
  self.assertEqual(price_tick("3500000"),Decimal("1000"))
 def test_price_rounding(self):
  self.assertEqual(snap_price("3500555","BUY"),Decimal("3500000"))
  self.assertEqual(snap_price("3500555","SELL"),Decimal("3501000"))
 def test_valid_minimum(self):
  self.assertEqual(validate_order("BUY","3500000","0.002")["notional_krw"],"7000.000")
  with self.assertRaises(ValueError):validate_order("BUY","3500001","0.003")
  with self.assertRaises(ValueError):validate_order("BUY","3500000","0.001")
 def test_margin(self):
  self.assertEqual(roundtrip_margin("0.14","0.05"),Decimal("0.04"))
  self.assertEqual(roundtrip_margin("0.14","0.05","0.03"),Decimal("-0.02"))
if __name__=="__main__":unittest.main()
