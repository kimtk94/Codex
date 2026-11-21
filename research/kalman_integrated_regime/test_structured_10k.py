"""Offline checks for 40-axis structured joint study and budget/size-matched report."""
import json
from pathlib import Path
import tempfile
import unittest

from research.kalman_integrated_regime import joint_policy as joint
from research.kalman_integrated_regime.structured_10k import (
    GATES, MANAGEMENT, GATE_BUDGETS, active_budget, generate_structured,
)
from research.kalman_integrated_regime.structured_report import summarize_structured


class StructuredTests(unittest.TestCase):
    def test_exact_joint_strata_not_outcome_guided(self):
        a, report = generate_structured(500, seed=29)
        b, report2 = generate_structured(500, seed=29)
        self.assertEqual(a, b)
        self.assertEqual(report, report2)
        self.assertEqual(len(a), 501)
        self.assertEqual(len(GATES), 20)
        self.assertEqual(len(MANAGEMENT), 20)
        self.assertEqual(len(joint.AXES), 40)
        self.assertEqual(a[0], joint.BASELINE)
        self.assertEqual(len({joint.policy_id(p) for p in a}), 501)
        self.assertTrue(all(joint.policy_valid(p) for p in a))
        self.assertEqual(report["gate_budget_counts"], {str(k):100 for k in GATE_BUDGETS})
        for tier in GATE_BUDGETS:
            self.assertEqual(sum(active_budget(p)==tier for p in a[1:]), 100)
        for axis in joint.AXES:
            with self.subTest(axis=axis):
                self.assertGreater(len({p[axis] for p in a[1:]}), 1)
        self.assertTrue(report["outcome_blind"])
        self.assertTrue(report["not_uniform_over_full_40dim_space"])

    def test_random_50pct_is_not_return_scaling(self):
        from research.kalman_integrated_regime.joint_policy import simulate_trade
        import pandas as pd
        p = dict(joint.BASELINE, size=1., tp=.03, sl=.03)
        c = dict(p, size=.5)
        day=(pd.Timestamp("2025-03-03"),
             pd.DataFrame([{"open":100., "high":104., "low":99., "close":103.}]))
        x=simulate_trade(p,[day],0,pd.Timestamp("2025-02-28"),100.)
        y=simulate_trade(c,[day],0,pd.Timestamp("2025-02-28"),100.)
        self.assertEqual(x.fills_buy,y.fills_buy)
        self.assertLess(abs(2*y.net_pnl-x.net_pnl),1e-7)

    def test_missing_exposure_results_are_rejected(self):
        # Real report never silently substitutes missing 50%-size counterfactuals.
        policies, generator = generate_structured(10,seed=20)
        with tempfile.TemporaryDirectory() as folder:
            files=[]
            for shard in (0,1):
                rows=[]
                for index,p in enumerate(policies):
                    if index%2 != shard:
                        continue
                    for year in (2025,2026):
                        for model in ("price_only","integrated_regime"):
                            rows.append({
                                "config_index":index,
                                "policy_id":joint.policy_id(p),"year":year,
                                "model":model,"params":p,
                                "return_pct":-2.0,"mdd_daily_mark_pct":-3.,
                                "trades":20, "active_filter_gates":active_budget(p),
                                "matched_50pct_return_pct":-1.,
                                "matched_50pct_mdd_pct":-1.5,
                                "matched_50pct_trades":20})
                payload={"shards":2,"shard":shard,"configs_total":11,
                         "structured_candidates":10,"baseline_control":1,
                         "generator":generator,"full_factorial_count":100000000,
                         "pairwise_coverage":{"covered":1,"possible":3},
                         "rows":rows}
                path=Path(folder)/f"joint_shard_{shard}.json"
                path.write_text(json.dumps(payload))
                files.append(path)
            report=summarize_structured(files,11)
            self.assertEqual(report["full_trade_models_by_year"],44)
            self.assertEqual(report["filter_budget_stats_excluding_baseline"]["integrated_regime"]["4"]["candidate_configs"],2)
            self.assertEqual(report["matched50_rankings_qualified_only"]["price_only"][0]["matched_50pct_return_2026_ytd_pct"],-1.)
            p=json.loads(files[0].read_text())
            p["rows"][0].pop("matched_50pct_return_pct")
            files[0].write_text(json.dumps(p))
            with self.assertRaisesRegex(ValueError,"MISSING_MATCHED_ALLOCATION_FIELDS"):
                summarize_structured(files,11)


if __name__ == "__main__":
    unittest.main()
