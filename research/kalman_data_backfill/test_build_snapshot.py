"""Research PIT ingestion: tests of no-imputation, four-NYSE-session labels."""
import unittest
import pandas as pd
import exchange_calendars as xcals
from build_snapshot import canonicalize,label_gate

class ResearchGateTests(unittest.TestCase):
    def setUp(self):
        self.cal=xcals.get_calendar('XNYS')
        sessions=self.cal.sessions_in_range('2026-10-01','2026-10-23')
        self.daily=pd.DatetimeIndex([self.cal.session_open(s) for s in sessions])

    def test_last_four_sessions_have_no_outcome(self):
        gate=label_gate(self.daily,self.daily,self.cal)
        self.assertEqual(int(gate.sum()),len(self.daily)-4)
        self.assertTrue(gate.iloc[0])
        self.assertFalse(gate.iloc[-1])

    def test_missing_bar_removes_previous_four_sessions(self):
        gap=self.daily[7]
        available=self.daily.difference(pd.DatetimeIndex([gap]))
        gate=label_gate(self.daily,available,self.cal)
        for i in (3,4,5,6,7):self.assertFalse(bool(gate.iloc[i]))
        self.assertTrue(bool(gate.iloc[2]))
        self.assertTrue(bool(gate.iloc[8]))

    def test_nyse_early_close_does_not_assume_26_bars(self):
        starts=[]
        for s in self.cal.sessions_in_range('2025-11-24','2025-12-05'):
            starts.extend(pd.date_range(self.cal.session_open(s),
                                        self.cal.session_close(s),
                                        freq='15min',inclusive='left'))
        idx=pd.DatetimeIndex(starts)
        day=idx.tz_convert('America/New_York').strftime('%Y-%m-%d')
        self.assertEqual(int((day=='2025-11-28').sum()),14)
        gate=label_gate(idx,idx,self.cal)
        self.assertTrue(bool(gate.iloc[0]))
        self.assertFalse(bool(gate.iloc[-1]))

    def test_unknown_quote_volume_is_not_fabricated(self):
        ts=pd.Timestamp('2026-10-29T13:30:00Z')
        f=pd.DataFrame({'_start':[ts],'candle_time_utc':[ts],
                        'open':[10.],'high':[11.],'low':[9.],
                        'close':[10.5],'volume':[100.]})
        result=canonicalize(f,'QQQ','15m','original')
        self.assertTrue(pd.isna(result['quote_volume'].iloc[0]))
        self.assertEqual(result['unit_min'].iloc[0],15)
        self.assertEqual(result['adjustment_basis'].iloc[0],'original_unknown')

if __name__=='__main__':unittest.main()
