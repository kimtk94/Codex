import unittest
from pathlib import Path

import pandas as pd

from research.regime_countertrend.fresh_oos import (
    ANCHOR,stitch,validate_price_rows,evaluate_oos
)

SOURCE=Path("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")

class FreshOOSBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h=pd.read_csv(SOURCE)
    def sample(self):
        frames={}
        for sym in ("QQQ","QLD"):
            anchor=float(self.h.iloc[-1][f"close_{sym.lower()}"])
            frames[sym]=pd.DataFrame([
              {"date":ANCHOR,"open":anchor,"high":anchor+.5,"low":anchor-.5,
                 "close":anchor,"volume":1000},
              {"date":"2026-09-08","open":anchor,"high":anchor+.8,"low":anchor-.6,
                 "close":anchor+.2,"volume":2000},
              {"date":"2026-09-09","open":anchor+.2,"high":anchor+1,"low":anchor-.3,
                 "close":anchor+.3,"volume":2200}
            ])
        return frames
    def test_source_cutoff_appends_only_new_days(self):
        combined,meta=stitch(self.h,self.sample(),minimum_recent="2026-09-09")
        self.assertEqual(len(combined),len(self.h)+2)
        self.assertEqual(combined.date_ny.iloc[-1],"2026-09-09")
        self.assertEqual(combined.date_ny.iloc[len(self.h)-1],ANCHOR)
        self.assertFalse(combined.date_ny.duplicated().any())
        self.assertAlmostEqual(meta["QLD"]["price_basis_factor"],1.)
    def test_missing_qlq_day_is_rejected(self):
        frames=self.sample()
        frames["QLD"]=frames["QLD"][frames["QLD"].date!="2026-09-09"]
        with self.assertRaises(ValueError):
            stitch(self.h,frames,minimum_recent="2026-09-08")
    def test_bad_anchor_basis_rejected(self):
        frames=self.sample()
        frames["QLD"].loc[0,"close"]*=.8
        with self.assertRaises(ValueError):
            stitch(self.h,frames,minimum_recent="2026-09-09")
    def test_duplicate_and_bad_bar_rejected(self):
        a=self.sample()["QQQ"]
        with self.assertRaises(ValueError):
            validate_price_rows(pd.concat([a,a.iloc[[0]]]),"QQQ")
        a.loc[1,"high"]=a.loc[1,"low"]-.1
        with self.assertRaises(ValueError):
            validate_price_rows(a,"QQQ")
    def test_without_new_data_is_explicit_hold(self):
        e,summary,meta=evaluate_oos(self.h,self.h)
        self.assertEqual(meta["status"],"INSUFFICIENT_FRESH_SIGNALS")
        self.assertTrue(e.empty)
if __name__=="__main__": unittest.main()
