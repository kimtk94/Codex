"""Contracts for pinned-original COIN model reconstruction, no secrets/bars."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location(
  "reconstruct_original",Path(__file__).with_name("reconstruct_pinned_original.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SyntheticPanels:
    def __init__(self,n,counts):
        self.dates=[f"DATE_{i}" for i in range(n)]
        self.signals={k:FakeArray([True]*v+[False]*(n-v)) for k,v in counts.items()}
    def __getitem__(self,key):
        return {"dates":self.dates,"signals":self.signals}[key]

class FakeArray:
    def __init__(self,data):self.data=data
    def sum(self):return sum(self.data)

class PinnedSourceContracts(unittest.TestCase):
    def test_exact_twenty_cohort_reproductions(self):
        panels={(sym,y):{"dates":[1]*208,
                 "signals":{a:FakeArray([True]*n+[False]*(208-n))
                            for a,n in models.items()}}
                for sym,years in m.EXPECTED_COUNTS.items()
                for y,models in years.items()}
        self.assertEqual(m.check_signal_counts(panels),m.EXPECTED_COUNTS)
        panels[("COIN",2025)]["signals"]["V_unweighted"]=FakeArray([True]*79+[False]*129)
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SIGNAL_PARITY_MISMATCH"):
            m.check_signal_counts(panels)
    def test_independent_annual_return_parity(self):
        r={"by_symbol":{
            sym:{str(year):{"policies":{"NEXT_RTH_CLOSE":{"arms":{
              "V_unweighted":{"cumulative_return_pct":value}}}}}
                 for year,value in years.items()}
            for sym,years in m.EXPECTED_EOD_V.items()
        }}
        self.assertEqual(len(m.check_eod_original(r)),5)
        r["by_symbol"]["COIN"]["2025"]["policies"]["NEXT_RTH_CLOSE"]["arms"]["V_unweighted"]["cumulative_return_pct"]+=.01
        with self.assertRaisesRegex(ValueError,"ORIGINAL_RETURN_PARITY_MISMATCH"):
            m.check_eod_original(r)
    def test_frozen_sha_provenance(self):
        self.assertEqual(len(m.PINNED_ORIGIN_SHA),40)
        self.assertEqual(m.ORIGINAL_RUN_ID,41217666574)
        self.assertEqual(sum(m.EXPECTED_COUNTS["COIN"][y]["V_unweighted"]
                             for y in (2025,2026)),126)

if __name__=="__main__": unittest.main()
