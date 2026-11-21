import unittest
import numpy as np
import pandas as pd
from research.regime_countertrend.correlated_factor_model import FEATURES,feature_frame
from research.regime_countertrend.feature_coverage_v3 import (
    FullCoverageFactorTransformer,group_feature_audit
)

class FeatureCoverageV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices=pd.read_csv("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
        cls.history=feature_frame(cls.prices)
        cls.train=cls.history[cls.history.date_ny<"2025-01-01"].dropna()
    def test_exact_20_columns_used(self):
        model,meta=group_feature_audit(self.prices)
        self.assertEqual(meta["raw_feature_count"],20)
        self.assertEqual(meta["model_input_coverage"],20)
        self.assertEqual(meta["omitted_features"],[])
        self.assertEqual(len(meta["residual_low_correlation_group"]),3)
        self.assertEqual(len(model.factor_names),8)
        self.assertEqual(set(FEATURES),set(model.used_features))
        self.assertEqual(set(model.used_features),set(x["feature"] for x in model.lineage))
    def test_unrelated_features_retain_full_rank(self):
        model=FullCoverageFactorTransformer().fit(self.train)
        last=self.train.tail(4).copy()
        before=model.transform(last)
        for col in model.residual_block:
            shifted=last.copy()
            shifted[col]+=0.5
            change=np.linalg.norm(model.transform(shifted)-before,axis=1)
            self.assertTrue((change>1e-8).all(),msg=col)
    def test_no_future_training_leakage(self):
        baseline=FullCoverageFactorTransformer().fit(self.train)
        data=self.history.copy()
        data.loc[data.date_ny>="2025-01-01","qld_rv20"]=100
        other=FullCoverageFactorTransformer().fit(
            data[data.date_ny<"2025-01-01"].dropna())
        self.assertEqual(baseline.blocks,other.blocks)
        np.testing.assert_allclose(baseline.transform(self.train.tail(10)),
                                   other.transform(self.train.tail(10)),atol=1e-10)
    def test_reject_missing_singletons_in_scoring(self):
        model=FullCoverageFactorTransformer().fit(self.train)
        with self.assertRaises(ValueError):
            model.transform(self.train.drop(columns=["rsi_delta3"]))
if __name__=="__main__":unittest.main()
