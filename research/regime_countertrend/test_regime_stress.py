import json
import unittest
from pathlib import Path
import pandas as pd
from research.regime_countertrend.failure_diagnostics import run as proxy_signals
from research.regime_countertrend.robust_walkforward import audit as robust_audit
from research.regime_countertrend.regime_stress import (
    audit,annotated,matched_placebo,group_summary
)
PRICES=Path("research/regime_countertrend/data/QLD_QQQ_daily_alignment.csv")
OUT=Path("results/regime_countertrend/regime_stress")

class RegimeStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prices=pd.read_csv(PRICES)
        event_candidates,_=proxy_signals(prices)
        cls.events,_,cls.walkforward,_=robust_audit(
            prices,event_candidates[["date","event"]])
    def test_no_selection_count_leakage(self):
        e=annotated(self.events,self.walkforward)
        chosen=self.walkforward[self.walkforward.label=="WALK_FORWARD_SELECTED"]
        self.assertEqual(len(e),56)
        self.assertEqual(int(e.selected.sum()),int(chosen.taken.sum()))
        self.assertEqual(int(chosen.query("year==2026").taken.iloc[0]),0)
    def test_random_placebo_reproducible(self):
        e=annotated(self.events,self.walkforward)
        x=matched_placebo(e,200,seed=20261103)
        y=matched_placebo(e,200,seed=20261103)
        self.assertEqual(x,y)
        self.assertFalse(x["valid_independent_significance_test"])
        self.assertEqual(x["method"],"EXACT_ENUMERATION")
        self.assertEqual(x["possible_selection_patterns"],168)
        self.assertEqual(x["random_equally_or_better_patterns"],76)
        self.assertAlmostEqual(x["descriptive_one_sided_placebo_probability"],76/168,places=12)
    def test_year_regime_rows_reconcile(self):
        e=annotated(self.events,self.walkforward)
        g=group_summary(e)
        self.assertEqual(int(g.opportunities.sum()),56)
        self.assertEqual(int(g.selected.sum()),int(e.selected.sum()))
    def test_robust_risk_and_artifacts(self):
        groups,regime,cost,loo,result=audit(
            self.events,self.walkforward,n_draws=2000)
        self.assertFalse(result["approval_allowed"])
        self.assertEqual(result["n_opportunities"],56)
        self.assertEqual(result["risk_all"]["n"],56)
        self.assertEqual(result["risk_selected"]["n"],result["selected_n"])
        self.assertIn("DOWN_RALLY",regime.event.tolist())
        self.assertEqual(set(cost.return_source),
            {"net_20bp","net_40bp","net_80bp","bestcase_net_20bp"})
        self.assertEqual(len(loo),7)
        self.assertEqual(result["placebo"]["matched_within"],
            "year_and_regime; fixed number of selected signals")
        OUT.mkdir(parents=True,exist_ok=True)
        for name,df in (("annual_regime.csv",groups),
          ("regime_concentration.csv",regime),
          ("cost_barrier_stress.csv",cost),
          ("leave_one_year_out.csv",loo)):
            df.to_csv(OUT/name,index=False)
        (OUT/"decision.json").write_text(json.dumps(result,indent=2))
        print("REGIME_STRESS_RESULTS",json.dumps(result))
        print("REGIME_STRESS_BY_YEAR",groups.to_json(orient="records"))
        print("REGIME_STRESS_BY_COST",cost.to_json(orient="records"))
if __name__=="__main__": unittest.main()
