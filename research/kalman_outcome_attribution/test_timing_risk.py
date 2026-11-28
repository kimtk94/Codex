import unittest
import numpy as np
import pandas as pd
from timing_risk import relative_features


class TimingRiskContracts(unittest.TestCase):
    def fixture(self):
        idx=pd.date_range("2020-01-01",periods=420,freq="B")
        rng=np.random.default_rng(123)
        return pd.Series(100*np.exp(np.cumsum(rng.normal(.0004,.018,len(idx)))),index=idx)

    def test_future_observations_cannot_change_prior_timing_features(self):
        close=self.fixture()
        cut=close.index[320]
        a=relative_features(close)
        close.loc[close.index>cut]*=5
        pd.testing.assert_frame_equal(a.loc[:cut],relative_features(close).loc[:cut])
        self.assertTrue(a.loc[cut].notna().all())

    def test_relative_vol_normalizer_excludes_signal_observation(self):
        c=self.fixture()
        r=c.pct_change(fill_method=None).rolling(20,min_periods=20).std()
        i=c.index[-1]
        expected=np.log(r.loc[i]/r.iloc[-253:-1].median())
        self.assertAlmostEqual(relative_features(c).loc[i,"relative_vol"],expected)

    def test_scale_invariant_and_missing_history_not_filled(self):
        c=self.fixture()
        a=relative_features(c)
        pd.testing.assert_frame_equal(a,relative_features(c*10),check_exact=False,
                                      rtol=1e-10,atol=1e-10)
        self.assertTrue(a.iloc[:126].isna().all().all())
        self.assertTrue(a.iloc[-1].notna().all())


if __name__=="__main__":
    unittest.main()
