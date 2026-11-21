import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.cross_sectional import screen

class CrossSectionalTests(unittest.TestCase):
    def fixture(self):
        n=100
        dates=pd.bdate_range("2025-01-01",periods=n)
        blocks=[]
        for symbol,scale in [("QQQ",1),("A",1),("B",1),("C",1)]:
            close=100*np.exp(np.arange(n)*.002*scale)
            if symbol=="A":close[75:81]*=.90
            blocks.append(pd.DataFrame({"date":dates,"symbol":symbol,"close":close,"sector":"TECH"}))
        return pd.concat(blocks,ignore_index=True)
    def test_outlier(self):
        e,m=screen(self.fixture())
        self.assertTrue((e.symbol=="A").any())
        self.assertTrue((e.type=="UP_IDIOSYNCRATIC_WEAK").any())
    def test_duplicate_rejected(self):
        p=self.fixture()
        with self.assertRaises(ValueError):screen(pd.concat([p,p.iloc[:1]]))
    def test_no_future_change_to_past_events(self):
        p=self.fixture()
        first,_=screen(p)
        p.loc[(p.symbol=="A")&(p.date==p.date.max()),"close"]*=10
        second,_=screen(p)
        cutoff=p.date.max()-pd.Timedelta(days=15)
        f=first[first.date<cutoff][["date","symbol","type"]].reset_index(drop=True)
        s=second[second.date<cutoff][["date","symbol","type"]].reset_index(drop=True)
        pd.testing.assert_frame_equal(f,s)
