import unittest
import pandas as pd
from research.regime_countertrend.intraday_coverage import analyze_frame, audit_folder

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
    def test_frozen_market_data_coverage(self):
        import json
        from pathlib import Path
        rows=audit_folder("research/regime_countertrend/data/price_15m")
        self.assertEqual(len(rows),5)
        output=Path("results/regime_countertrend/price_15m")
        output.mkdir(parents=True,exist_ok=True)
        (output/"coverage.json").write_text(json.dumps({"source":"FROZEN_DRIVE_15M_PRICE_ONLY","results":rows},indent=2))
        for row in rows:
            print("INTRADAY_PRICE_AUDIT",json.dumps(row,ensure_ascii=False))
            self.assertEqual(row["status"],"PRICE_COVERAGE_ONLY_NOT_FILLS")
            self.assertGreater(row["adjacent_15m_pairs"],10)
    def test_prices_invalid_rejected(self):
        s=self.sample();s.loc[2,"high"]=98.
        self.assertEqual(analyze_frame(s,"INTC")["status"],"HOLD_INCONSISTENT_OHLC_RANGE")
if __name__=="__main__":unittest.main()
