"""Offline tests: real source timestamps, not job success, govern recovery."""
import datetime as dt
import pathlib,sys,unittest
from zoneinfo import ZoneInfo
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from report_fallback_gate import SOURCE_HEADER
from report_slot_recovery import inspect,latest_due
KST=ZoneInfo("Asia/Seoul")
def at(h,m=0):return dt.datetime(2026,10,30,h,m,tzinfo=KST)
def grid(received="2026-10-30 12:00:05 KST",checked="2026-10-30 15:25:40 KST"):
 return [SOURCE_HEADER.copy()]+[[n,received,checked,"493","493","0","0","a"*64,"PRESERVED_NO_NEW_REPORT","QQ IMAP"] for n in ("Leads","Opportunities","Quotation")]
class RecoveryTests(unittest.TestCase):
 def test_before_first_due(self):
  self.assertIsNone(latest_due(at(9,39)))
  self.assertFalse(inspect(grid(),at(9,39))[0])
 def test_missing_17h_retry_after_grace(self):
  self.assertFalse(inspect(grid(),at(17,39))[0])
  refresh,reason,slot=inspect(grid(),at(18,10))
  self.assertTrue(refresh)
  self.assertEqual(reason,"MISSING_REPORT_FOR_SLOT_RETRY_INGEST")
  self.assertEqual(slot,"2026-10-30 17:00 KST")
 def test_throttle_stale_and_recheck_later(self):
  g=grid(checked="2026-10-30 17:41:00 KST")
  self.assertFalse(inspect(g,at(18,10))[0])
  self.assertTrue(inspect(g,at(20,12))[0])
 def test_valid_17h_all_three_skips(self):
  self.assertFalse(inspect(grid(received="2026-10-30 17:00:05 KST"),at(20,12))[0])
 def test_partial_delivery_fails_slot_but_preserves_others(self):
  g=grid(received="2026-10-30 17:01:00 KST")
  g[2][1]="2026-10-30 12:00:05 KST"
  self.assertTrue(inspect(g,at(20,12))[0])
 def test_missed_09h_and_12h(self):
  self.assertTrue(inspect(grid("2026-10-29 17:00:05 KST","2026-10-29 18:00:00 KST"),at(9,45))[0])
  self.assertTrue(inspect(grid("2026-10-30 09:00:05 KST","2026-10-30 09:40:00 KST"),at(12,40))[0])
 def test_unverified_rows_fail_closed(self):
  g=grid();g[1][8]="OTHER"
  with self.assertRaisesRegex(ValueError,"UNVERIFIED"):inspect(g,at(18,10))
  g=grid();g[1][7]="no_sha"
  with self.assertRaisesRegex(ValueError,"HASH"):inspect(g,at(18,10))
  with self.assertRaisesRegex(ValueError,"ENTITY_MISSING"):inspect(grid()[:-1],at(18,10))
 def test_future_stamps_refused(self):
  with self.assertRaisesRegex(ValueError,"IN_FUTURE"):
   inspect(grid(checked="2026-11-01 18:00:00 KST"),at(18,10))
 def test_successful_check_is_not_fresh_report(self):
  g=grid(checked="2026-10-30 17:41:00 KST")
  self.assertFalse(inspect(g,at(18,10))[0])
  self.assertTrue(inspect(g,at(20,12))[0])
 def test_same_day_grace(self):
  self.assertEqual(latest_due(at(12,45)).hour,12)
  self.assertEqual(latest_due(at(17,40)).hour,17)
if __name__=="__main__":unittest.main()
