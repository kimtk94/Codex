import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.analyze import analyze

class TestRegime(unittest.TestCase):
    def data(self):
        n=150
        qqq=100*np.exp(np.arange(n)*.002)
        qld=100*np.exp(np.arange(n)*.004)
        qld[90:96] *= .94
        return pd.DataFrame({"date_ny":pd.date_range("2024-01-02",periods=n,freq="B"),"close_qqq":qqq,"close_qld":qld})
    def test_event_and_nonoverlap(self):
        events,meta=analyze(self.data())
        self.assertGreaterEqual(len(events),1)
        self.assertEqual(events.event.iloc[0],"UP_DIP")
        self.assertTrue((events.qld_future5.notna()).all())
    def test_no_future_leakage(self):
        d=self.data()
        first,_=analyze(d)
        d.loc[d.index[-2:],"close_qld"] *= 10
        second,_=analyze(d)
        a=first[first.date_ny<d.date_ny.iloc[-10]]
        b=second[second.date_ny<d.date_ny.iloc[-10]]
        self.assertEqual(a[["date_ny","event"]].to_json(),b[["date_ny","event"]].to_json())
    def test_duplicate_dates_rejected(self):
        d=self.data()
        d.loc[1,"date_ny"]=d.loc[0,"date_ny"]
        with self.assertRaises(ValueError): analyze(d)
if __name__=="__main__": unittest.main()
