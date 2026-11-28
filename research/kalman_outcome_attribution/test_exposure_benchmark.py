import unittest
import pandas as pd
import numpy as np
from exposure_benchmark import benchmark, perf

class ExposureBenchmarkTests(unittest.TestCase):
    def test_exposure_lag_and_cost(self):
        r=pd.Series([0.,.1,-.2,.03])
        exposure=pd.Series([.5,1.,0.,.9])
        b,w,t=benchmark(r,exposure)
        np.testing.assert_allclose(w,[0,.5,1.,0.])
        np.testing.assert_allclose(b,[0,.05,-.2,0.])
        self.assertAlmostEqual(t.iloc[2],1-.55/1.05)
        paid,_,_=benchmark(r,exposure,10)
        np.testing.assert_allclose(b-paid,t*.001)
        exposure.iloc[-1]=.1
        pd.testing.assert_series_equal(benchmark(r,exposure)[0],b)

    def test_drawdown_from_initial_capital(self):
        p=perf(pd.Series([-.1,.1]))
        self.assertAlmostEqual(p["total_return"],-.01)
        self.assertAlmostEqual(p["max_drawdown"],-.1)

    def test_invalid_exposure_or_return_holds(self):
        for x in ([0,1.01],[0,np.nan]):
            with self.assertRaisesRegex(ValueError,"INVALID_EXPOSURE"):
                benchmark(pd.Series([0.,.1]),pd.Series(x))
        with self.assertRaisesRegex(ValueError,"INVALID_BENCHMARK_INPUT"):
            benchmark(pd.Series([0.,-1.]),pd.Series([0.,1.]))
