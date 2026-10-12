import tempfile,unittest,csv
from pathlib import Path
from v24_research import read_data,sweep
class ResearchTest(unittest.TestCase):
 def test_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.csv';p.write_text('timestamp,close\n2026-01-01T00:00:00+00:00,100\n2026-01-01T00:00:00+00:00,101\n')
   with self.assertRaises(ValueError):read_data(p)
 def test_realistic_hour_gaps_not_claimed_missing(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.csv';p.write_text('timestamp,close\n2026-01-01T15:00:00+00:00,100\n2026-01-02T15:00:00+00:00,101\n')
   self.assertEqual(read_data(p)[1]['gaps_gt_2h'],1)
 def test_sweep_output(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.csv';p.write_text('timestamp,close\n2026-01-01T15:00:00+00:00,100\n2026-01-01T16:00:00+00:00,99\n2026-01-01T17:00:00+00:00,102\n2026-01-01T18:00:00+00:00,100\n')
   out=Path(d)/'out.csv';m=sweep(p,out,spacings=('0.14',),levels=(20,100));self.assertEqual(m['scenario_count'],2);self.assertEqual(len(list(csv.DictReader(out.open()))),2)
if __name__=='__main__':unittest.main()
