import tempfile
import unittest
from pathlib import Path
from coverage_audit import audit

class CoverageTests(unittest.TestCase):
    def test_snapshot_not_mistaken_for_history(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/"daily.csv";s=Path(td)/"snapshot.csv"
            d.write_text("date_ny,close_qqq,close_qld\n2026-01-02,10,20\n2026-01-05,11,22\n")
            s.write_text("market,timeframe,candle_time_utc,open,high,low,close,volume\nQQQ,15m,2026-01-05T14:30:00Z,1,2,1,2,10\nQQQ,1h,2026-01-05T14:30:00Z,1,2,1,2,10\n")
            a=audit(d,s)
            self.assertEqual(a["daily"]["rows"],2)
            self.assertEqual(len(a["latest"]["groups"]),2)
            self.assertFalse(a["training_intraday_ready"])
            self.assertEqual(a["alpaca_entitlement"],"NOT_VERIFIED")

    def test_duplicate_daily_date(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/"d.csv";s=Path(td)/"s.csv"
            d.write_text("date_ny,close_qqq,close_qld\n2026-01-02,1,2\n2026-01-02,1,2\n")
            s.write_text("market,timeframe,candle_time_utc,open,high,low,close,volume\nQQQ,15m,2026-01-05T14:30:00Z,1,2,1,2,10\n")
            self.assertEqual(audit(d,s)["daily"]["duplicate_dates"],1)

if __name__=="__main__":
    unittest.main()
