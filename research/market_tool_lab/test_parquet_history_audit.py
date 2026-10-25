import tempfile
import unittest
from pathlib import Path

import pandas as pd
from parquet_history_audit import audit

class ParquetHistoryTests(unittest.TestCase):
    def test_hourly_utc_parquet(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"QQQ_1h.parquet"
            dates=pd.date_range("2026-10-21T13:30:00Z",periods=4,freq="h")
            pd.DataFrame({"open":[1,2,3,4],"high":[2,3,4,5],"low":[1,2,3,4],
                "close":[2,3,4,5],"volume":[10,20,30,40]},index=dates).to_parquet(path)
            r=audit(path)
            self.assertEqual(r["rows"],4)
            self.assertEqual(r["duplicate_timestamps"],0)
            self.assertEqual(r["sessions_observed"],1)
            self.assertEqual(r["column_quality"]["close"]["missing"],0)

    def test_duplicate_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"duplicate.parquet"
            t=pd.Timestamp("2026-10-21T13:30:00Z")
            pd.DataFrame({"close":[1,2]},index=pd.DatetimeIndex([t,t])).to_parquet(path)
            self.assertEqual(audit(path)["duplicate_timestamps"],1)

    def test_reject_missing_timezone(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"naive.parquet"
            pd.DataFrame({"close":[1]},index=pd.DatetimeIndex(["2026-10-21 13:30:00"])).to_parquet(path)
            with self.assertRaises(ValueError):
                audit(path)

if __name__=="__main__":
    unittest.main()
