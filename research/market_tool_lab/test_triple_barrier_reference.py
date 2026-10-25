import unittest
from triple_barrier_reference import triple_barrier

def bar(c,h=None,l=None):
    return {"close":c,"high":h if h is not None else c,"low":l if l is not None else c}
class TripleBarrierReferenceTests(unittest.TestCase):
    def test_take_profit(self):
        x=triple_barrier([bar(100),bar(101,104,99)],0)
        self.assertEqual(x["reason"],"TP")
        self.assertAlmostEqual(x["gross_return"],0.03)
    def test_stop_loss(self):
        x=triple_barrier([bar(100),bar(99,100,96)],0)
        self.assertEqual(x["reason"],"SL")
        self.assertAlmostEqual(x["gross_return"],-0.03)
    def test_simultaneous_stop_first(self):
        x=triple_barrier([bar(100),bar(100,105,95)],0)
        self.assertEqual(x["reason"],"SL")
        self.assertTrue(x["simultaneous_barrier"])
    def test_timeout_four_days(self):
        x=triple_barrier([bar(100)]+[bar(100)]*4,0)
        self.assertEqual((x["reason"],x["exit_idx"]),("TIME",4))
    def test_end_of_data_is_not_normal_timeout(self):
        x=triple_barrier([bar(100),bar(100)],0)
        self.assertEqual(x["reason"],"DATA_END")
    def test_no_future_data(self):
        with self.assertRaises(ValueError):
            triple_barrier([bar(100)],0)

if __name__=="__main__":
    unittest.main()
