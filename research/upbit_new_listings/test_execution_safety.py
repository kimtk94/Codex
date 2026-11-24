import unittest
from datetime import datetime,timezone,timedelta
from execution_safety import conservative_exit,validate_candles,trailing_exit,first_utc_day

def bar(minute,o,h,l,c):
 return dict(t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=minute),o=o,h=h,l=l,c=c,v=100)

class Safety(unittest.TestCase):
 def test_stop_and_take_same_bar_stop_first(self):
  fill,why=conservative_exit(bar(0,100,125,95,110),97,120,0)
  self.assertEqual((fill,why),(97,"stop"))
 def test_gap_below_stop_never_fills_at_stop(self):
  fill,why=conservative_exit(bar(0,90,96,87,92),97,120,0)
  self.assertEqual((fill,why),(90,"gap_stop"))
 def test_take_on_gap_conservative_target(self):
  fill,why=conservative_exit(bar(0,125,135,122,130),97,120,0)
  self.assertEqual((fill,why),(120,"take"))
 def test_trailing_stop_cannot_use_current_bar_high(self):
  bars=[bar(0,100,120,99,118),bar(15,116,117,106,110)]
  r=trailing_exit(bars,0,trail_pct=.1,buy_slippage=0,sell_slippage=0,fee=0)
  self.assertEqual(r["exit_idx"],1)
  self.assertEqual(r["reason"],"stop")
  self.assertAlmostEqual(r["fill"],108)
 def test_irregular_bars_visible(self):
  issues=validate_candles([bar(0,100,101,99,100),bar(30,100,102,99,101)])
  self.assertIn((1,"missing_or_irregular_candle"),issues)
 def test_invalid_ohlc(self):
  issues=validate_candles([bar(0,100,99,98,100)])
  self.assertIn((0,"invalid_ohlc"),issues)
 def test_utc_first_date(self):
  t=datetime(2026,10,24,0,15,tzinfo=timezone.utc)
  self.assertEqual(str(first_utc_day(t)),"2026-10-24")
if __name__=="__main__":unittest.main()
