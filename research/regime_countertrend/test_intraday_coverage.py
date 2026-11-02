import unittest
import pandas as pd
from research.regime_countertrend.intraday_coverage import analyze_frame

class PriceCoverageTests(unittest.TestCase):
    def sample(self):
        dates=pd.date_range("2026-10-01T13:30:00Z",periods=26,freq="15min")
        return pd.DataFrame({"date":dates,"open":[100.]*26,"high":[101.]*26,
             "low":[99.]*26,"close":[100.]*26,"volume":[1000]*26})
    def test_full_regular_session(self):
        r=analyze_frame(self.sample(),"INTC")
        self.assertEqual(r["status"],"PRICE_COVERAGE_ONLY_NOT_FILLS")
        self.assertEqual(r["rth_full_26bar_days"],1)
        self.assertEqual(r["adjacent_15m_pairs"],25)
    def test_duplicate_time_rejected(self):
        s=self.sample()
        s.loc[1,"date"]=s.loc[0,"date"]
        self.assertEqual(analyze_frame(s,"INTC")["status"],"HOLD_INVALID_OR_DUPLICATE_TIMESTAMPS")
    def test_prices_invalid_rejected(self):
        s=self.sample();s.loc[2,"high"]=98.
        self.assertEqual(analyze_frame(s,"INTC")["status"],"HOLD_INCONSISTENT_OHLC_RANGE")
if __name__=="__main__":unittest.main()
