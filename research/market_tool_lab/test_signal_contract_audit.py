import tempfile,unittest
from pathlib import Path
from signal_contract_audit import evaluate
B="date_ny,open_qqq,high_qqq,low_qqq,close_qqq,open_qld,high_qld,low_qld,close_qld\n"+"".join(f"2026-01-0{i},100,100,100,100,100,100,100,100\n" for i in range(1,7))
class SignalTests(unittest.TestCase):
 def run_case(self,rows):
  with tempfile.TemporaryDirectory() as t:
   b=Path(t)/"bars.csv";s=Path(t)/"signals.csv"
   b.write_text(B);s.write_text("date_ny,symbol,signal,strategy,regime\n"+rows)
   return evaluate(b,s)
 def test_group(self):
  r=self.run_case("2026-01-01,QQQ,1,R5.2,RANGE\n")
  self.assertEqual(r["groups"][0]["events"],1)
  self.assertEqual(r["status"],"DESCRIPTIVE_ONLY")
 def test_duplicate(self):
  with self.assertRaises(ValueError):
   self.run_case("2026-01-01,QQQ,1,R5.2,RANGE\n2026-01-01,QQQ,1,R5.2,RANGE\n")
 def test_no_hindsight_fake_symbol(self):
  with self.assertRaises(ValueError):
   self.run_case("2026-01-01,FAKE,1,R5.2,RANGE\n")
 def test_missing_day(self):
  with self.assertRaises(ValueError):
   self.run_case("2026-02-01,QQQ,1,R5.2,RANGE\n")
if __name__=="__main__": unittest.main()
