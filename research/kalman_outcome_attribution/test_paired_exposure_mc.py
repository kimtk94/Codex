import unittest
import numpy as np
import pandas as pd
from paired_exposure_mc import joint_indices,path_metrics,simulate

class PairedExposureMonteCarloTests(unittest.TestCase):
    def test_year_stratification(self):
        dates=pd.to_datetime(["2024-12-30","2024-12-31","2025-01-02","2025-01-03","2025-01-06"])
        ix=joint_indices(np.random.default_rng(42),dates,60,30,True)
        self.assertEqual(ix.shape,(30,5))
        self.assertTrue((ix[:,:2]<2).all())
        self.assertTrue((ix[:,2:]>=2).all())
    def test_initial_capital_in_drawdown(self):
        f,d=path_metrics(np.array([[[-.1], [.1]]]))
        self.assertAlmostEqual(f[0,0],-.01)
        self.assertAlmostEqual(d[0,0],-.1)
    def test_identical_series_never_underperform(self):
        dates=pd.date_range("2025-01-01",periods=40)
        v=np.tile(np.linspace(-.01,.01,len(dates))[:,None],(1,6))
        r=simulate(v,dates,5,True,repetitions=40)
        for row in r["scenarios"]:
            for b in row["benchmarks"].values():
                self.assertEqual(b["underperform_fraction"],0)
                self.assertEqual(b["excess_p05_p50_p95"],[0,0,0])
    def test_invalid_returns_rejected(self):
        for bad in (np.nan,-1,np.inf):
            with self.assertRaisesRegex(ValueError,"INVALID_MC_RETURNS"):
                path_metrics(np.array([[[bad]]]))
