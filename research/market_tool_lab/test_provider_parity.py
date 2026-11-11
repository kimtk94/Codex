import tempfile
import unittest
from pathlib import Path
from provider_parity import compare

BASE="date_ny,open_qld,high_qld,low_qld,close_qld,volume_qld,open_qqq,high_qqq,low_qqq,close_qqq,volume_qqq\n2026-01-02,20,22,19,21,200,10,11,9,10.5,100\n"
PROVIDER="date,symbol,open,high,low,close,volume\n2026-01-02,QQQ,10,11,9,10.5,100\n2026-01-02,QLD,20,22,19,21,200\n"

class ParityTests(unittest.TestCase):
    def check(self,content):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td)/"baseline.csv";p=Path(td)/"provider.csv"
            b.write_text(BASE);p.write_text(content)
            return compare(b,p)
    def test_exact(self):
        x=self.check(PROVIDER)
        self.assertEqual(x["status"],"COMPARABLE")
        self.assertEqual(x["overlap_records"],2)
    def test_1pct_gap_is_review(self):
        x=self.check(PROVIDER.replace("10.5,100","11,100"))
        self.assertEqual(x["status"],"REVIEW")
        self.assertEqual(x["close_gap_gt_tolerance"],1)
    def test_missing_day_is_tracked(self):
        x=self.check("date,symbol,open,high,low,close,volume\n2026-01-02,QQQ,10,11,9,10.5,100\n")
        self.assertEqual(x["baseline_only"],1)
    def test_duplicate_provider_key_is_review(self):
        x=self.check(PROVIDER+"2026-01-02,QQQ,10,11,9,10.5,100\n")
        self.assertEqual(x["duplicate_provider_keys"],1)
        self.assertEqual(x["status"],"REVIEW")
