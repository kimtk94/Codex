"""Research-only synthetic contract tests for archived aggregate acceptance gate."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("coin_result_gate",Path(__file__).with_name("coin_result_gate.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture():
    x={"schema":"coin-structure-rr2-all-sessions-pilot-v1",
       "status":"RESEARCH_ONLY_NOT_MODEL_SIGNAL_MATCHED","live":"HOLD",
       "min_net_rr":2.0,"roundtrip_cost_fraction":.003,
       "max_stop_fraction":.03,"max_target_fraction":.08,
       "signal_cohort":"ALL_COMPLETE_EXCHANGE_SESSIONS_NOT_V_UNWEIGHTED_SIGNALS",
       "quality":{"expected_sessions":711,"complete_sessions":711,
                  "incomplete_sessions":0},"results":[]}
    for year in (2024,2025,2026):
        for arm in m.ARMS:
            for hold in m.HOLDS:
                r=.4 if year==2024 and arm=="ORL_PRIOR20_HIGH" and hold in (2,4) else -.1
                if year==2026 and arm=="PRIOR_LOW_BUFFER_2R" and hold==2: r=.2
                x["results"].append({"year":year,"arm":arm,"hold_sessions":hold,
                    "trades":25,"geometry_pass":30,"all_sessions_after_warmup":220,
                    "mean_R":r,"mean_net_pct":r,
                    "total_return_pct":r*5,"eod_mdd_pct":-15,
                    "cost_stress_50bp_planned_rr2_count":0,
                    "cost_stress_100bp_planned_rr2_count":0,
                    "cost_stress_50bp_mean_R":r-.1,
                    "cost_stress_100bp_mean_R":r-.2})
    return x

class ReviewGateTests(unittest.TestCase):
    def _run(self,data,sha=None):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"aggregate.json"
            p.write_text(json.dumps(data))
            return m.review(p,sha)
    def test_select_2024_only_and_hold_2025_2026(self):
        r=self._run(fixture())
        self.assertEqual(r["2024_selection"]["arm"],"ORL_PRIOR20_HIGH")
        self.assertEqual(r["2024_selection"]["hold_sessions"],2)
        self.assertEqual(r["both_positive_2025_2026"],0)
        self.assertFalse(r["eligible_for_live"])
        self.assertEqual([v["year"] for v in r["validation"]],[2025,2026])
        self.assertEqual(r["cost_50bp_2R_breaches"],24*25)
        self.assertEqual(r["cost_100bp_2R_breaches"],24*25)
        self.assertTrue(r["cost_increase_requires_new_ex_ante_target"])
    def test_fail_closed_on_nonmatched_relabel(self):
        x=fixture();x["status"]="PRODUCTION_GO"
        with self.assertRaisesRegex(ValueError,"UNSAFE_LIVE_STATE"): self._run(x)
        x=fixture();x["signal_cohort"]="V_unweighted_MODEL_MATCHED"
        with self.assertRaisesRegex(ValueError,"MATCHED_SIGNAL_FALSE_CLAIM"): self._run(x)
        x=fixture();x["quality"]["incomplete_sessions"]=1
        with self.assertRaisesRegex(ValueError,"SIP_COVERAGE_DRIFT"): self._run(x)
    def test_fail_closed_on_missing_cost_stress_evidence(self):
        x=fixture()
        x["results"][0].pop("cost_stress_50bp_planned_rr2_count")
        with self.assertRaisesRegex(ValueError,"INVALID_COST_REPRICED_RR2_COUNT"):
            self._run(x)

    def test_require_full_complete_grid_and_hash(self):
        x=fixture();x["results"].pop()
        with self.assertRaisesRegex(ValueError,"MISSING_CELLS"): self._run(x)
        with self.assertRaisesRegex(ValueError,"SOURCE_SHA_MISMATCH"): self._run(fixture(),"deadbeef")
if __name__=="__main__":unittest.main()
