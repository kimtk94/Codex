import unittest
from upbit_maintenance_v42 import classify_gap,premaintenance_cancel
from upbit_maintenance_paper_v42 import run_maintenance_aware
class TestJulyMaintenance(unittest.TestCase):
 def test_exact_event_only(self):
  self.assertEqual(classify_gap("2026-07-05T17:00:00+00:00","2026-07-05T21:51:00+00:00","KRW-BTC"),"EXCHANGE_MAINTENANCE_20260706")
  self.assertIsNone(classify_gap("2026-07-05T17:00:00+00:00","2026-07-05T21:50:00+00:00","KRW-BTC"))
 def test_cancel_policy(self):
  self.assertTrue(premaintenance_cancel("BUY","101","100"))
  self.assertTrue(premaintenance_cancel("SELL","99","100"))
  self.assertFalse(premaintenance_cancel("BUY","100","100"))
  self.assertFalse(premaintenance_cancel("SELL","100","100"))
 def test_gap_no_phantom_fill(self):
  data=[("2026-07-05T17:00:00+00:00","3500000"),("2026-07-05T21:51:00+00:00","3300000")]
  r=run_maintenance_aware(data,"KRW-ETH")
  self.assertEqual(r["fills"],0)
  self.assertEqual(len(r["maintenance_events"]),1)
  self.assertTrue(r["maintenance_events"][0]["restart_fill_blocked"])
if __name__=="__main__":unittest.main()
