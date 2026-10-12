import unittest
from decimal import Decimal
from upbit_v38_cost_stress import COSTS,GAPS,MODES,MARKETS
class TestV38(unittest.TestCase):
 def test_dimensions(self):self.assertEqual(len(MARKETS)*len(GAPS)*len(MODES)*len(COSTS),48)
 def test_positive_monotone_costs(self):
  fees=[Decimal('0.05')+Decimal(x) for x in COSTS]
  self.assertEqual(fees,sorted(set(fees)))
if __name__=='__main__':unittest.main()
