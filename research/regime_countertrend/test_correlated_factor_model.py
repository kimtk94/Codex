import json
import unittest
from pathlib import Path
import pandas as pd
from research.regime_countertrend.failure_diagnostics import run as proxy_signals
from research.regime_countertrend.robust_walkforward import build_events
from research.regime_countertrend.correlated_factor_model import (
    FEATURES, feature_frame, correlation_groups, CorrelatedFactors, apply_models
)

SOURCE=Path("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
OUT=Path("results/regime_countertrend/cfm_v2")

class CorrelatedFactorV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prices=pd.read_csv(SOURCE)
    def test_groups_share_2plus_columns_and_drop_orphans(self):
        daily=feature_frame(self.prices)
        before=daily[daily.date_ny<"2025-01-01"].dropna()
        groups,orphans=correlation_groups(before)
        self.assertGreaterEqual(len(groups),2)
        self.assertTrue(all(len(g)>=2 for g in groups))
        self.assertEqual(sum(len(g) for g in groups)+len(orphans),len(FEATURES))
        self.assertFalse(any(set(g)&set(orphans) for g in groups))
        self.assertEqual(len(groups),5)
        self.assertEqual(sum(len(g) for g in groups),17)
    def test_no_future_price_in_features(self):
        changed=self.prices.copy()
        before=feature_frame(self.prices)
        changed.loc[len(changed)-1,"close_qqq"]*=1.25
        after=feature_frame(changed)
        pd.testing.assert_frame_equal(before.iloc[:-1],after.iloc[:-1])
    def test_group_pca_is_fit_only_on_past(self):
        daily=feature_frame(self.prices)
        train=daily[daily.date_ny<"2025-01-01"].dropna()
        a=CorrelatedFactors().fit(train)
        changed=daily.copy()
        changed.loc[changed.date_ny>="2025-01-01","qqq_ret20"]=999
        b=CorrelatedFactors().fit(changed[changed.date_ny<"2025-01-01"].dropna())
        self.assertEqual(a.groups,b.groups)
        import numpy as np
        np.testing.assert_allclose(a.transform(train.tail(7)),b.transform(train.tail(7)),rtol=1e-12)
    def test_real_proxy_annual_walkforward_and_artifacts(self):
        event_raw,_=proxy_signals(self.prices)
        events=build_events(self.prices,event_raw[["date","event"]])
        self.assertEqual(len(events),64)
        folds,pred,groups,report=apply_models(self.prices,events)
        self.assertFalse(report["promotion_allowed"])
        self.assertEqual(report["status"],"HOLD_EXPLORATORY_GROUPED_MODEL")
        self.assertEqual(set(report["evaluated_folds"]),{2022,2023,2024,2025,2026})
        self.assertEqual(len(pred),39)
        self.assertTrue(all(folds[folds.status=="FITTED"].factor_groups>=2))
        self.assertTrue((pred.group_prob.between(0,1)).all())
        self.assertTrue((pred.raw_prob.between(0,1)).all())
        self.assertEqual(set(folds[folds.status=="FITTED"].model),
            {"BASELINE","GROUPED_PCA_RIDGE","RAW_COLUMN_RIDGE"})
        for _,r in folds[folds.status=="FITTED"].iterrows():
            self.assertLess(r.train_last_exit,f"{r.year}-01-01")
        OUT.mkdir(parents=True,exist_ok=True)
        folds.to_csv(OUT/"annual_grouped_model_comparison.csv",index=False)
        pred.to_csv(OUT/"signal_probabilities.csv",index=False)
        groups.to_csv(OUT/"feature_groups_by_training_fold.csv",index=False)
        (OUT/"decision.json").write_text(json.dumps(report,indent=2))
        print("CFM_V2_GROUPS",groups[groups.trained_before_year==2025].to_json(orient="records"))
        print("CFM_V2_RESULT",json.dumps(report))
        print("CFM_V2_ANNUAL",folds[folds.status=="FITTED"].to_json(orient="records"))
if __name__=="__main__":unittest.main()
