import unittest
import pandas as pd
from research.regime_countertrend.signal_scarcity import diagnose
from research.regime_countertrend.fresh_intraday import coverage

class SignalScarcityAndIntradayTests(unittest.TestCase):
    def test_research_boundary_and_pending_horizon(self):
        history=pd.read_csv("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
        sample=history.iloc[-2:].copy()
        sample["date_ny"]=["2026-09-08","2026-09-09"]
        days,report=diagnose(history,sample)
        self.assertEqual(report["new_days"],2)
        self.assertEqual(report["pending_horizon_days"],2)
        self.assertFalse(report["promotion_allowed"])
    def test_intraday_full_day_and_time_alignment(self):
        t=pd.date_range("2026-10-01T13:30:00Z",periods=26,freq="15min")
        bar=pd.DataFrame({"ts_utc":t.astype(str),"date_ny":["2026-10-01"]*26,
             "local_time":t.tz_convert("America/New_York").strftime("%H:%M"),
             "open":[100.]*26,"high":[101.]*26,"low":[99.]*26,
             "close":[100.]*26,"volume":[200]*26})
        daily=pd.DataFrame([{"date_ny":"2026-10-01","open_qld":100.}])
        _,days,report=coverage(bar,"QLD",daily)
        self.assertEqual(report["full_26bar_sessions"],1)
        self.assertEqual(report["first_15m_open_match_count"],1)
        self.assertAlmostEqual(report["max_abs_first_open_vs_daily_pct"],0.)
        self.assertFalse(report["promotion_allowed"])
        b=bar.drop(index=2)
        _,partial,r=coverage(b,"QLD",daily)
        self.assertEqual(r["incomplete_sessions"],1)
        self.assertFalse(partial.full_26_regular_bars.iloc[0])
    def test_intraday_duplicate_and_ohlc_rejected(self):
        t=pd.date_range("2026-10-01T13:30:00Z",periods=26,freq="15min")
        b=pd.DataFrame({"ts_utc":t.astype(str),"date_ny":["2026-10-01"]*26,
             "local_time":t.tz_convert("America/New_York").strftime("%H:%M"),
             "open":[100.]*26,"high":[101.]*26,"low":[99.]*26,
             "close":[100.]*26,"volume":[200]*26})
        daily=pd.DataFrame([{"date_ny":"2026-10-01","open_qld":100.}])
        duplicate=pd.concat([b,b.iloc[[0]]],ignore_index=True)
        with self.assertRaises(ValueError):coverage(duplicate,"QLD",daily)
        b.loc[0,"high"]=98.
        with self.assertRaises(ValueError):coverage(b,"QLD",daily)
if __name__=="__main__":unittest.main()
