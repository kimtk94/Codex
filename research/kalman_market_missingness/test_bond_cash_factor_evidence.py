import unittest
import pandas as pd

from bond_cash_factor_evidence import compare_cash_event, audit_cash_events


class BondCashEvidenceTest(unittest.TestCase):
    def test_exact_cash_factor_pattern_is_never_approval(self):
        r = compare_cash_event(100,99,98,98,1)
        self.assertEqual(r["status"],"CASH_FACTOR_PATTERN_CONSISTENT_UNCERTIFIED_HOLD")
        self.assertAlmostEqual(r["residual_bp"],0)
    def test_constant_ratio_does_not_match_cash_event(self):
        self.assertEqual(compare_cash_event(100,99,98,97.02,1)["status"],
                         "CASH_FACTOR_PATTERN_MISMATCH_HOLD")
    def test_invalid_inputs_fail_closed(self):
        for value in (0,float("nan"),float("inf"),100,-1):
            self.assertEqual(compare_cash_event(100,99,98,98,value)["status"],
                             "INVALID_PRICE_INPUT_HOLD")
    def test_cutoff_and_missing_pair_distinguished(self):
        dates=pd.to_datetime(["2026-08-31","2026-09-01","2026-10-01","2026-10-30"],utc=True)
        a=pd.DataFrame({"timestamp":dates,"is_adjusted":False,
                        "open":100.,"high":101.,"low":99.,"close":100.})
        b=a.copy()
        b["is_adjusted"]=True
        b.loc[0,"close"]=100-.435025
        r=audit_cash_events(a,b,"yf_hyg","2026-11-25")
        self.assertEqual(r[0]["status"],"CASH_FACTOR_PATTERN_CONSISTENT_UNCERTIFIED_HOLD")
        self.assertEqual(r[1]["status"],"CONSECUTIVE_PAIR_MISSING_HOLD")
        self.assertEqual(r[2]["status"],"AFTER_SOURCE_COVERAGE_NO_PAIRED_FACTOR_HOLD")
        self.assertTrue(all(not x["factor_certified"] and not x["issuer_amount_certified"]
                            and x["approved_backfill_rows"]==0 for x in r))
        self.assertEqual(audit_cash_events(a,b,"yf_hyg","2026-10-30")[2]["status"],
                         "AFTER_REFERENCE_ASOF_HOLD")
        self.assertEqual(audit_cash_events(b,a,"yf_hyg","2026-11-25")[0]["status"],
                         "PRICE_BASIS_UNSUITABLE_HOLD")
