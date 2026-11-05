import tempfile
import unittest
from pathlib import Path
from source_audit import audit_alignment, audit_snapshot

class SourceAuditTests(unittest.TestCase):
    def test_daily_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.csv"
            p.write_text("date_ny,open_qld,high_qld,low_qld,close_qld,volume_qld,open_qqq,high_qqq,low_qqq,close_qqq,volume_qqq\n2026-01-02,1,2,1,2,10,3,4,3,4,20\n")
            r=audit_alignment(p)
            self.assertTrue(r["training_ready"])
            self.assertEqual(r["rows"],1)

    def test_snapshot_is_not_training_history(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"s.csv"
            p.write_text("market,timeframe,candle_time_utc,open,high,low,close,volume\nQQQ,1d,2026-01-02T14:30:00+00:00,1,2,1,2,10\nQQQ,15m,2026-01-02T14:30:00+00:00,1,2,1,2,10\n")
            r=audit_snapshot(p)
            self.assertFalse(r["training_ready"])
            self.assertEqual(len(r["groups"]),2)
            self.assertFalse(r["violations"])

    def test_snapshot_duplicate_group_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"s.csv"
            header="market,timeframe,candle_time_utc,open,high,low,close,volume\n"
            line="QQQ,15m,2026-01-02T14:30:00+00:00,1,2,1,2,10\n"
            p.write_text(header+line+line)
            self.assertEqual(audit_snapshot(p)["violations"]["duplicate_symbol_timeframe_timestamp"],1)

if __name__=="__main__":
    unittest.main()
