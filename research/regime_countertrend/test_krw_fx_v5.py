import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.krw_fx_v5 import (
    previous_fx_marks,attach_fx,build_entry_dates,summarize,parse_fx_chart
)

class KRWFXTests(unittest.TestCase):
    def fx(self):
        return pd.DataFrame({"date":["2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07"],
                             "usdkrw_close":[1400.,1420.,1390.,1370.,1360.]})
    def event(self):
        return pd.DataFrame([{"date":"2026-10-01","entry_date":"2026-10-02",
            "exit_date":"2026-10-06","symbol":"AMD","net_20bp":.02}])
    def test_currency_direction_flip(self):
        trades=attach_fx(self.event(),self.fx())
        self.assertAlmostEqual(trades.entry_fx_close_previous_session.iloc[0],1400.)
        self.assertAlmostEqual(trades.exit_fx_close_previous_session.iloc[0],1390.)
        self.assertAlmostEqual(trades.krw_mark_return.iloc[0],1.02*1390/1400-1)
        self.assertLess(trades.krw_mark_return.iloc[0],trades.usd_net_return.iloc[0])
        self.assertLess(trades.krw_roundtrip_fx_25bps_each_side.iloc[0],
                        trades.krw_roundtrip_fx_10bps_each_side.iloc[0])
        self.assertLess(trades.krw_roundtrip_fx_10bps_each_side.iloc[0],
                        trades.krw_mark_return.iloc[0])
    def test_positive_usd_return_can_be_krw_loss(self):
        t=self.event();t.loc[0,"net_20bp"]=.02
        fx=self.fx();fx.loc[fx.date=="2026-10-05","usdkrw_close"]=1350.
        r=attach_fx(t,fx)
        self.assertTrue(r.usd_win.iloc[0])
        self.assertFalse(r.krw_mark_win.iloc[0])
    def test_previous_fx_close_must_precede_trade(self):
        marks=previous_fx_marks(["2026-10-02","2026-10-05","2026-10-06"],self.fx())
        self.assertEqual(marks.fx_reference_date.tolist(),
                         ["2026-10-01","2026-10-02","2026-10-05"])
        self.assertTrue((marks.fx_age_calendar_days>0).all())
    def test_missing_fx_is_hard_hold_not_zero(self):
        t=self.event();t.loc[0,"exit_date"]="2026-10-21"
        with self.assertRaises(ValueError):attach_fx(t,self.fx())
    def test_reject_quote_inverse(self):
        fx=self.fx();fx.loc[:,"usdkrw_close"]=1/1400.
        with self.assertRaises(ValueError):attach_fx(self.event(),fx)
    def test_next_stock_session_entry(self):
        frame=pd.DataFrame({"date":["2026-10-01","2026-10-02","2026-10-05","2026-10-06"]})
        e=pd.DataFrame([{"symbol":"AMD","date":"2026-10-01",
                         "exit_date":"2026-10-02","net_20bp":-.032}])
        result=build_entry_dates(e,{"AMD":frame})
        self.assertEqual(result.entry_date.iloc[0],"2026-10-02")
    def test_krw_win_rate_and_sample_alignment(self):
        r=attach_fx(self.event(),self.fx())
        out=summarize(r,{"ALL_TRADES":np.array([True])})
        self.assertEqual(len(out),4)
        self.assertEqual(set(out.quote_type),{"USD","KRW_MARK",
           "KRW_CONVERT_10BPS_SIDE","KRW_CONVERT_25BPS_SIDE"})
    def test_fx_source_timestamp_parsing(self):
        import json
        timestamps=[int(x.timestamp()) for x in pd.date_range("2026-10-01T17:00:00Z",periods=3,freq="D")]
        raw={"chart":{"result":[{"timestamp":timestamps,
            "indicators":{"quote":[{"close":[1400,1390,1380]}]}}]}}
        data=parse_fx_chart(json.dumps(raw).encode())
        self.assertEqual(len(data),3)
        self.assertAlmostEqual(data.usdkrw_close.iloc[0],1400.)
if __name__=="__main__":unittest.main()
