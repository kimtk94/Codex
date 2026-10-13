import csv,tempfile,unittest
from pathlib import Path
from upbit_data_audit_v28 import parse,audit
from upbit_v39_monthly_collect import months_between
class TestMonthlyQuality(unittest.TestCase):
 def test_naive_is_utc(self):
  self.assertEqual(parse("2026-07-01T00:00:00"),parse("2026-07-01T00:00:00Z"))
 def test_month_rollover(self):
  self.assertEqual(list(months_between("2025-12","2026-02")),[(2025,12),(2026,1),(2026,2)])
 def test_missing_boundary_is_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"candles.csv"
   with p.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["t","o","h","l","c","v"])
    w.writeheader()
    for minute in (1,2,3):
     w.writerow({"t":f"2026-09-01T00:0{minute}:00+00:00","o":"100","h":"100","l":"100","c":"100","v":"1"})
   result=audit(p,1,"2026-09-01T00:00:00Z","2026-09-01T00:03:00Z")
   self.assertEqual(result["status"],"BLOCKED_DATA_QUALITY")
 def test_complete_window_pass(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"candles.csv"
   with p.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["t","o","h","l","c","v"])
    w.writeheader()
    for minute in range(4):
     w.writerow({"t":f"2026-09-01T00:0{minute}:00+00:00","o":"100","h":"100","l":"100","c":"100","v":"1"})
   self.assertEqual(audit(p,1,"2026-09-01T00:00:00Z","2026-09-01T00:03:00Z")["status"],"PASS")
if __name__=="__main__":unittest.main()
