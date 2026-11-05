import csv
import tempfile
import unittest
from pathlib import Path
from ohlcv_audit import validate

class OHLCVAuditTests(unittest.TestCase):
    def make_csv(self, rows):
        f=tempfile.TemporaryDirectory()
        path=Path(f.name)/"data.csv"
        with path.open("w",newline="") as handle:
            writer=csv.writer(handle)
            writer.writerow(["timestamp","open","high","low","close","volume"])
            writer.writerows(rows)
        self.addCleanup(f.cleanup)
        return path

    def test_valid(self):
        p=self.make_csv([
            ["2026-10-01T09:30:00-04:00",100,102,99,101,1000],
            ["2026-10-01T09:45:00-04:00",101,103,100,102,1200]])
        self.assertEqual(validate(p)["status"],"PASS")
        self.assertEqual(validate(p)["rows"],2)

    def test_duplicate_timestamp_fails(self):
        p=self.make_csv([
            ["2026-10-01T09:30:00-04:00",100,102,99,101,1000],
            ["2026-10-01T09:30:00-04:00",100,102,99,101,1000]])
        self.assertEqual(validate(p)["status"],"FAIL")

    def test_impossible_candle_fails(self):
        p=self.make_csv([["2026-10-01T09:30:00-04:00",100,99,98,101,100]])
        self.assertEqual(validate(p)["status"],"FAIL")

    def test_naive_timezone_fails(self):
        p=self.make_csv([["2026-10-01T09:30:00",100,102,99,101,100]])
        self.assertEqual(validate(p)["status"],"FAIL")

if __name__=="__main__":
    unittest.main()
