#!/usr/bin/env python3
"""Deterministic sensitivity checks; source simulator remains unchanged."""
import unittest
from test_grid_v3_regression import run, bar

class Sensitivity(unittest.TestCase):
    def test_equal_touch_vs_one_tick_cross(self):
        base=[bar(0)]
        equal=run(base+[bar(1,l=1_980_000)])
        crossed=run(base+[bar(1,l=1_979_500)])
        self.assertEqual(equal["fills"],0)
        self.assertGreater(crossed["fills"],0)
        self.assertGreater(crossed["fees_krw"],0)

    def test_fee_rate_changes_net_result_for_same_one_fill(self):
        candles=[bar(0),bar(1,h=2_000_000,l=1_979_500,c=2_000_000)]
        free=run(candles,fee=0)
        charged=run(candles,fee=.001)
        costly=run(candles,fee=.002)
        self.assertEqual(free["fills"],charged["fills"])
        self.assertEqual(charged["fills"],costly["fills"])
        self.assertGreater(free["return_pct"],charged["return_pct"])
        self.assertGreater(charged["return_pct"],costly["return_pct"])
        self.assertEqual(free["fees_krw"],0)
        self.assertGreater(costly["fees_krw"],charged["fees_krw"])

    def test_order_budget_can_prevent_fill(self):
        # With capital 100k and 100 levels, unit=1k < 5k exchange minimum.
        candles=[bar(0),bar(1,l=1_000_000,h=2_000_000,c=2_000_000)]
        r=run(candles,capital=100_000,n=100)
        self.assertEqual(r["fills"],0)
        self.assertEqual(r["fees_krw"],0)

if __name__=="__main__":
    unittest.main(verbosity=2)
