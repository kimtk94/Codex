import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.stock_relative import analyze

class StockRelativeTests(unittest.TestCase):
    def sample(self):
        dates=pd.bdate_range("2024-01-02",periods=140)
        rows=[]
        for sym in ["QQQ","AAPL","AMZN","IONQ"]:
            close=100*np.exp(np.arange(len(dates))*.002)
            if sym=="AAPL":
                close[100:105]*=.88
            for date,val in zip(dates,close):
                rows.append({"symbol":sym,"date":date,"close":val})
        return pd.DataFrame(rows)
    def test_signal_and_future_separation(self):
        panel=self.sample()
        events,s=analyze(panel)
        self.assertTrue((events.symbol=="AAPL").any())
        self.assertTrue((events.event=="UP_WEAK").any())
        cutoff=panel.date.max()-pd.Timedelta(days=15)
        early=events[events.date<cutoff][["date","symbol","event"]].reset_index(drop=True)
        panel.loc[(panel.symbol=="AAPL")&(panel.date==panel.date.max()),"close"]*=5
        new,_=analyze(panel)
        new_early=new[new.date<cutoff][["date","symbol","event"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(early,new_early)
    def test_duplicate_rejected(self):
        panel=self.sample()
        with self.assertRaises(ValueError):
            analyze(pd.concat([panel,panel.iloc[:1]],ignore_index=True))
if __name__=="__main__":unittest.main()
