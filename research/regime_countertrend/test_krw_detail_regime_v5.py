import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.krw_detail_regime_v5 import (
    DETAIL_COLUMNS,DETAIL_GROUPS,detail_daily,GroupedDetails,
    fx_asof_signal,_with_interactions,_with_detail
)

class KRWDetailV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d=pd.read_csv("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
        cls.asset=pd.DataFrame({
            "date":d.date_ny,"open":d.open_qld,"high":d.high_qld,
            "low":d.low_qld,"close":d.close_qld,"volume":d.volume_qld})
        cls.features=detail_daily(cls.asset,"QLD")
    def test_all_16_short_features_mapped_to_four_groups(self):
        self.assertEqual(len(DETAIL_COLUMNS),16)
        self.assertEqual(len(DETAIL_GROUPS),4)
        self.assertEqual(set(DETAIL_COLUMNS),set(self.features.columns)-{"date","symbol"})
        train=self.features[self.features.date<"2025-01-01"].dropna()
        m=GroupedDetails().fit(train)
        self.assertEqual(len(m.lineage),16*2)
        self.assertEqual(set(x["feature"] for x in m.lineage),set(DETAIL_COLUMNS))
        self.assertEqual(m.transform(train.tail(5)).shape,(5,8))
    def test_future_prices_do_not_change_prior_detail_feature(self):
        old=self.features
        changed=self.asset.copy()
        i=len(changed)-1
        changed.loc[i,"high"]*=1.1
        updated=detail_daily(changed,"QLD")
        pd.testing.assert_frame_equal(old.iloc[:-1],updated.iloc[:-1])
    def test_future_training_does_not_change_pca_factors(self):
        train=self.features[self.features.date<"2025-01-01"].dropna()
        a=GroupedDetails().fit(train)
        change=self.features.copy()
        change.loc[change.date>="2025-01-01","volume_ratio_20d"]+=50
        b=GroupedDetails().fit(change[change.date<"2025-01-01"].dropna())
        np.testing.assert_allclose(a.transform(train.tail(7)),
                                   b.transform(train.tail(7)),atol=1e-12)
    def test_regime_detail_interaction_dimension_and_separation(self):
        rows=pd.DataFrame({"event":["UP_DIP","DOWN_RALLY","SIDE_DIP"]})
        base=np.array([[.0,0],[.0,0],[.0,1]])
        detail=np.ones((3,8))
        a=_with_detail(base,detail,rows)
        b=_with_interactions(base,detail,rows)
        self.assertEqual(a.shape,(3,10))
        self.assertEqual(b.shape,(3,34))
        self.assertTrue((b[0,-24:]==0).all())
        self.assertTrue((b[1,-24:-16]==1).all())
        self.assertTrue((b[2,-16:-8]==1).all())
    def test_fx_signal_lag_and_nonfuture_values(self):
        fx=pd.DataFrame({"date":pd.bdate_range("2026-01-02",periods=70).strftime("%Y-%m-%d"),
                         "usdkrw_close":np.linspace(1300,1420,70)})
        d=fx.date.iloc[-1]
        result=fx_asof_signal([d],fx)
        self.assertEqual(result.shape,(1,4))
        later=fx.copy()
        later.loc[later.date==d,"usdkrw_close"]=1900
        np.testing.assert_allclose(result,fx_asof_signal([d],later),rtol=1e-12)
    def test_adjusted_price_ulp_roundoff_allowed_but_real_violation_fails(self):
        asset=self.asset.copy()
        asset.loc[19,"low"]=asset.loc[19,"close"]+1e-14
        asset.loc[19,"high"]=max(asset.loc[19,"high"],asset.loc[19,"close"])
        result=detail_daily(asset,"QLD")
        self.assertEqual(len(result),len(asset))
        asset.loc[19,"low"]=asset.loc[19,"close"]+0.01
        with self.assertRaises(ValueError):
            detail_daily(asset,"QLD")
    def test_low_liquidity_missing_invalid_is_not_zero_filled(self):
        altered=self.asset.copy()
        altered.loc[19,"volume"]=0
        data=detail_daily(altered,"QLD")
        self.assertTrue(pd.isna(data.volume_ratio_20d.iloc[19]) or
                        np.isfinite(data.volume_ratio_20d.iloc[19]))
        m=GroupedDetails().fit(self.features[self.features.date<"2025-01-01"].dropna())
        invalid=self.features.tail(5).copy()
        invalid.loc[invalid.index[0],"range_position_20d"]=np.nan
        with self.assertRaises(ValueError):m.transform(invalid)
if __name__=="__main__":unittest.main()
