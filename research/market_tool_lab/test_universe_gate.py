import tempfile
import unittest
from pathlib import Path
from universe_gate import check

class UniverseGateTests(unittest.TestCase):
 def test_threshold_and_duplicates(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"u.csv"
   header="symbol,market,first_seen_utc,last_seen_utc,source\n"
   rows=[f"US{i},US_STOCK,2020-01-01T00:00:00Z,2026-01-01T00:00:00Z,fixture" for i in range(120)]
   rows += [f"KRW-C{i},UPBIT_KRW,2020-01-01T00:00:00Z,2026-01-01T00:00:00Z,fixture" for i in range(80)]
   p.write_text(header+"\n".join(rows)+"\n")
   self.assertEqual(check(p)["status"],"PASS")
   p.write_text(header+"\n".join(rows+[rows[0]])+"\n")
   self.assertEqual(check(p)["status"],"FAIL")
 def test_insufficient_coverage(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"u.csv"
   p.write_text("symbol,market,first_seen_utc,last_seen_utc,source\nAAPL,US_STOCK,2020,2026,test\n")
   self.assertEqual(check(p)["status"],"FAIL")
if __name__=="__main__":unittest.main()
