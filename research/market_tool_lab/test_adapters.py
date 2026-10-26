import csv
import tempfile
import unittest
from pathlib import Path
from adapters import convert
from ohlcv_audit import validate

class AdaptersTests(unittest.TestCase):
    def test_alignment_to_qqq(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"a.csv"
            dst=Path(d)/"out.csv"
            src.write_text("date_ny,open_qqq,high_qqq,low_qqq,close_qqq,volume_qqq\n2026-01-05,10,11,9,10.5,100\n")
            self.assertEqual(convert(src,dst,"alignment","QQQ"),1)
            self.assertEqual(validate(dst)["status"],"PASS")
            with dst.open() as f:
                row=next(csv.DictReader(f))
            self.assertEqual(row["symbol"],"QQQ")

    def test_intraday_to_standard(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"bars.csv"
            dst=Path(d)/"out.csv"
            src.write_text("market,candle_time_utc,open,high,low,close,volume\nQQQ,2026-10-01 14:30:00+00:00,10,11,9,10.5,100\n")
            self.assertEqual(convert(src,dst,"etf_bars","QQQ"),1)
            self.assertEqual(validate(dst)["status"],"PASS")

if __name__ == "__main__":
    unittest.main()
