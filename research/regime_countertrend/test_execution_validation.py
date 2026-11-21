import unittest
import pandas as pd
from research.regime_countertrend.execution_validation import attribute

class ActualFillContractTests(unittest.TestCase):
    def sample(self):
        start=pd.Timestamp("2026-10-12T13:30:00Z")
        t=pd.DataFrame([{
          "trade_id":"DEMO_SYNTHETIC_ONLY","symbol":"QLD","side":"LONG",
          "signal_ts_utc":(start-pd.Timedelta(days=1)).isoformat(),
          "entry_ts_utc":start.isoformat(),
          "exit_ts_utc":(start+pd.Timedelta(minutes=75)).isoformat(),
          "entry_price":100.0,"exit_price":98.0,"quantity":10,
          "fees_usd":2.0,"intended_entry_price":99.8,
          "exit_reason":"STOP"
        }])
        bars=pd.DataFrame([
            {"symbol":"QLD","ts_utc":(start+pd.Timedelta(minutes=15*i)).isoformat(),
             "open":100.,"high":101.,"low":99.,"close":100.,"volume":1000}
            for i in range(5)])
        return t,bars
    def test_complete_hour_metrics_not_causal(self):
        t,b=self.sample()
        out,meta=attribute(t,b)
        self.assertTrue(out.first_hour_complete.iloc[0])
        self.assertEqual(out.full_bars.iloc[0],5)
        self.assertAlmostEqual(out.mae_first_hour.iloc[0],-.01,places=8)
        self.assertEqual(meta["status"],"COMPLETE")
        self.assertEqual(out.interpretation.iloc[0],"OBSERVATIONAL_NOT_CAUSAL")
    def test_partial_coverage_is_not_complete(self):
        t,b=self.sample()
        b=b[b.ts_utc!=b.ts_utc.iloc[1]]
        out,meta=attribute(t,b)
        self.assertFalse(out.first_hour_complete.iloc[0])
        self.assertEqual(meta["status"],"PARTIAL_INTRADAY_COVERAGE")
        self.assertTrue(pd.isna(out.mae_first_hour.iloc[0]))
    def test_slippage_is_null_without_intent(self):
        t,b=self.sample()
        t=t.drop(columns=["intended_entry_price"])
        out,meta=attribute(t,b)
        self.assertEqual(meta["missing_intended_entry_price"],1)
        self.assertTrue(pd.isna(out.signed_entry_slippage_bps.iloc[0]))
    def test_reject_duplicate_bar_and_bad_chronology(self):
        t,b=self.sample()
        with self.assertRaises(ValueError):
            attribute(t,pd.concat([b,b.iloc[[0]]],ignore_index=True))
        t.loc[0,"signal_ts_utc"]="2026-10-14T13:30:00Z"
        with self.assertRaises(ValueError):attribute(t,b)
    def test_fill_bar_excluded_when_fill_inside_bar(self):
        t,b=self.sample()
        t.loc[0,"entry_ts_utc"]="2026-10-12T13:37:00Z"
        out,meta=attribute(t,b)
        self.assertEqual(out.full_bars.iloc[0],4)
        self.assertFalse(out.first_hour_complete.iloc[0])
    def test_unavailable_target_is_not_reported_as_stop(self):
        t,b=self.sample()
        t=t.drop(columns=["exit_reason"])
        out,_=attribute(t,b)
        self.assertTrue(pd.isna(out.exit_reason_reported.iloc[0]))
if __name__=="__main__":unittest.main()
