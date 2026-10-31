"""Synthetic-only strict contract tests for original-model COIN statistical gate."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("coin_matched_stat_gate",Path(__file__).with_name("coin_matched_stat_gate.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    parity={sym:{str(y):{"P_unweighted":22,"V_unweighted":25}
                 for y in m.YEARS} for sym in m.SYMBOLS}
    eod={sym:{str(y):{"within_1e_5_percentage_points":True}
              for y in m.YEARS} for sym in m.SYMBOLS}
    rows=[]
    for y in m.YEARS:
        for a in m.ARMS:
            for h in m.HOLDS:
                c=80 if y==2025 else 46
                rows.append({
                    "year":y,"arm":a,"hold_sessions":h,
                    "trades":5,"original_signals":c,
                    "structural_pass":5,"first_rejection_counts":{"STOP_TOO_WIDE":c-5},
                    "overlap_blocked":0,"right_censored":0,
                    "target_count":2,"stop_count":3,"time_count":0,
                    "stop_gap_count":0,
                    "mean_R":-.2 if y==2025 else .25,
                    "eod_mdd_pct":-7.0,
                    "cost_stress_50bp_planned_rr2_count":0,
                    "cost_stress_100bp_planned_rr2_count":0,
                    "cost_stress_50bp_mean_R":-.3,
                })
    return {
        "schema":"coin-rr2-v-unweighted-pit-signal-replay-v1",
        "status":"MATCHED_LEDGER_RESEARCH_ONLY_NOT_UNSEEN_OOS",
        "live":"HOLD","not_fresh_oos":True,"no_broker_or_live_change":True,
        "signals_verified":{"2025":80,"2026":46},
        "quality":{"incomplete_sessions":0,"complete_sessions":711},
        "baseline_parity":{"2025":{"original_atr125_stop300_gate_pass":0},
                           "2026":{"original_atr125_stop300_gate_pass":0}},
        "provenance":{
            "original_commit":m.ORIGIN,"original_success_run":41217666574,
            "original_bar_count":221014,"can_promote_live":False,
            "type":"RECONSTRUCTED_SOURCE_NOT_ORIGINAL_SAVED_SIGNAL_LEDGER",
            "full_universe_signal_count_parity":parity,
            "full_universe_EOD_return_parity":eod,
        },
        "results":rows
    }


def validate(d,sha=None):
    with tempfile.TemporaryDirectory() as temp:
        f=Path(temp)/"aggregate.json"
        f.write_text(json.dumps(d))
        return m.audit(f,sha)


class StatisticalGateContracts(unittest.TestCase):
    def test_wilson_small_sample(self):
        self.assertAlmostEqual(m.wilson_lower(4,7),.25046,places=3)
        self.assertAlmostEqual(m.wilson_lower(0,7),0,places=12)
        self.assertIsNone(m.wilson_lower(0,0))
        with self.assertRaisesRegex(ValueError,"INVALID_BINOMIAL_COUNTS"):
            m.wilson_lower(8,7)

    def test_complete_causally_unpromotable_sample(self):
        d=validate(fixture())
        self.assertEqual(d["tested_configurations"],12)
        self.assertEqual(d["configurations_positive_in_both_years"],0)
        self.assertFalse(d["eligible_for_live"])
        self.assertEqual(d["status"],"SOURCE_PARITY_PASS_STATISTICAL_STABILITY_HOLD")

    def test_fail_closed_on_corrupted_source_or_duplicate_arm(self):
        x=fixture();x["provenance"]["original_commit"]="bogus"
        with self.assertRaisesRegex(ValueError,"SOURCE_LINEAGE_DRIFT"):
            validate(x)
        x=fixture();x["results"][0]["target_count"]=4
        with self.assertRaisesRegex(ValueError,"EXIT_TOTAL_MISMATCH"):
            validate(x)
        x=fixture();x["results"].append(x["results"][0])
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_OR_DUPLICATE_CELL"):
            validate(x)
        x=fixture();x["results"][0]["cost_stress_50bp_planned_rr2_count"]=6
        with self.assertRaisesRegex(ValueError,"INVALID_STRESSED_RR2_ELIGIBILITY"):
            validate(x)

    def test_hash_and_year_scope_strict(self):
        x=fixture()
        with self.assertRaisesRegex(ValueError,"ORIGINAL_MATCHED_AGGREGATE_SHA_DRIFT"):
            validate(x,"deadbeef")
        x["signals_verified"]["2026"]=45
        with self.assertRaisesRegex(ValueError,"COIN_126_SIGNAL_DRIFT"):
            validate(x)


if __name__=="__main__":
    unittest.main()
