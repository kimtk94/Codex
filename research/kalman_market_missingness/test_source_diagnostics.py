import unittest
import pandas as pd
from diagnose_source import fx_violations
from audit_missingness import effective_nyse_asof

class DiagnosticTests(unittest.TestCase):
 def test_ohlc_flags_open_outside_high(self):
  d=pd.DataFrame({'timestamp':['2026-10-01','2026-10-02'],
                  'open':[103,100],'high':[101,102],'low':[99,98],'close':[100,100]})
  x=fx_violations(d)
  self.assertEqual(len(x),1)
  self.assertTrue(bool(x.iloc[0].open_above_high))
  self.assertGreater(x.iloc[0].max_ohlc_violation_bps,0)
 def test_valid_ohlc_not_flagged(self):
  d=pd.DataFrame({'timestamp':['2026-10-01'],
                   'open':[100],'high':[101],'low':[99],'close':[100]})
  self.assertTrue(fx_violations(d).empty)
 def test_exchange_asof_rolls_through_weekend(self):
  self.assertEqual(effective_nyse_asof('2026-10-31T03:00:00Z'),'2026-10-30')
  self.assertEqual(effective_nyse_asof('2026-11-02T18:00:00Z'),'2026-10-30')
  self.assertEqual(effective_nyse_asof('2026-11-03T01:00:00Z'),'2026-11-02')
 def test_early_close_black_friday(self):
  self.assertEqual(effective_nyse_asof('2026-11-27T18:10:00Z'),'2026-11-25')
  self.assertEqual(effective_nyse_asof('2026-11-27T18:50:00Z'),'2026-11-27')