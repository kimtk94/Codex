"""Offline tests: no credentials, network, or production database access."""
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from research.quant_stack.flip_exit_replay_2026 import run_path, friday_due, prepare_bars

BASE = datetime(2026, 5, 12, 14, 0, tzinfo=timezone.utc)


def monitor(prices):
    return [{"t":BASE+timedelta(minutes=5*i),
             "end":BASE+timedelta(minutes=5*(i+1)),
             "o":p,"h":p,"l":p,"c":p,"v":1}
            for i,p in enumerate(prices)]


class Flip2026Tests(unittest.TestCase):
    def run_prices(self, prices, threshold, cap_minutes=30):
        return run_path(monitor(prices),100,BASE+timedelta(minutes=cap_minutes),
                        threshold,10,False)

    def test_two_negative_confirmations_after_arming(self):
        o=self.run_prices([100.30,99.79,99.78,101.0],-.002)
        self.assertEqual(o["reason"],"PROFIT_FLIP")
        self.assertAlmostEqual(o["gross"],-.0022)

    def test_not_armed_never_triggers_flip(self):
        o=self.run_prices([99.70,99.65,99.50,99.40],-.002,20)
        self.assertEqual(o["reason"],"MAX_HOLD_4")

    def test_wider_threshold_delays_and_can_recover(self):
        base=self.run_prices([100.3,99.75,99.74,100.50],-.002,20)
        wide=self.run_prices([100.3,99.75,99.74,100.50],-.01,20)
        self.assertEqual(base["reason"],"PROFIT_FLIP")
        self.assertEqual(wide["reason"],"MAX_HOLD_4")
        self.assertGreater(wide["net"],base["net"])

    def test_strict_stop_not_removed_when_flip_off(self):
        o=self.run_prices([101.0,99.70,96.0,102],None,20)
        self.assertEqual(o["reason"],"STOP_LOSS")

    def test_stop_precedes_flip(self):
        o=self.run_prices([101.0,96.50,96.00],-.005,20)
        self.assertEqual(o["reason"],"STOP_LOSS")

    def test_exit_never_after_cap(self):
        o=self.run_prices([101.0,101.1,99.1,99.0,99.0],None,15)
        self.assertEqual(o["reason"],"MAX_HOLD_4")
        self.assertAlmostEqual(o["gross"],-.009)

    def test_friday_in_dst(self):
        utc=datetime(2026,10,9,19,45,tzinfo=timezone.utc)
        self.assertTrue(friday_due(utc))
        self.assertFalse(friday_due(utc-timedelta(minutes=5)))

    def test_friday_before_stop_when_due_after_midday(self):
        utc=datetime(2026,10,9,19,40,tzinfo=timezone.utc)
        prices=[{"t":utc,"end":utc+timedelta(minutes=5),
                 "o":100.2,"h":100.2,"l":100.1,"c":100.2,"v":1}]
        o=run_path(prices,100,utc+timedelta(hours=1),None,10,True)
        self.assertEqual(o["reason"],"FRIDAY_FLAT")


if __name__=="__main__":
    unittest.main()
