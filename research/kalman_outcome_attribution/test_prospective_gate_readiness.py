import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
import exchange_calendars as xc
import pandas as pd

from prospective_gate_readiness import (
    gate_class, registration_status, verify_timing, verified_zip,
    verify_ancestry, sha, JOURNALS, PREFIX,
)


class ProspectiveGateContracts(unittest.TestCase):
    def setUp(self):
        self.cal=xc.get_calendar("XNYS")

    def test_gate_boundaries_missing_and_non_candidate(self):
        self.assertEqual(gate_class("BULL_LOGISTIC",True,{"ret5":-.01,"spy_mom5_lag":0.}),
                         "QUALIFIES")
        self.assertEqual(gate_class("BULL_LOGISTIC",True,{"ret5":0.,"spy_mom5_lag":0.}),
                         "COMPLEMENT")
        self.assertEqual(gate_class("BEAR_LOGISTIC",True,{"vix_lag":20.,"gld_mom5_lag":0.}),
                         "QUALIFIES")
        self.assertEqual(gate_class("BEAR_LOGISTIC",True,{"vix_lag":None,"gld_mom5_lag":0.}),
                         "ABSTAIN_MISSING_FEATURE")
        self.assertEqual(gate_class("BEAR_LOGISTIC",False,{}),"NOT_ORIGINAL_CANDIDATE")
        self.assertEqual(gate_class("BEAR_RULE",True,{}),"COVERAGE_CONTROL")

    def test_registration_boundary(self):
        for d in ("2026-11-20","2026-11-23","2026-11-24"):
            self.assertEqual(registration_status(self.cal,d),"EXCLUDED_BEFORE_REGISTRATION")
        self.assertEqual(registration_status(self.cal,"2026-11-25"),"IN_REGISTERED_WINDOW")
        self.assertEqual(registration_status(self.cal,"2027-11-24"),"IN_REGISTERED_WINDOW")
        self.assertEqual(registration_status(self.cal,"2027-11-26"),"EXCLUDED_AFTER_FIXED_WINDOW")

    def test_holiday_horizon_and_cost_arithmetic(self):
        s={"recorded_at_utc":"2026-11-25T22:00:00Z"}
        self.assertEqual(verify_timing(self.cal,"2026-11-25","2026-11-30",s,None),
                         "PENDING_FOUR_XNYS_SESSIONS")
        self.assertEqual(verify_timing(self.cal,"2026-11-25","2026-12-02",s,None),
                         "OVERDUE_MISSING_SETTLEMENT")
        e={"entry_date":"2026-11-27","exit_date":"2026-12-02",
           "recorded_at_utc":"2026-12-02T22:00:00Z",
           "entry_open":100.,"exit_close":103.,"gross_return":.03,
           "net_return_by_cost_bp":{"20":.028,"40":.026,"80":.022}}
        self.assertEqual(verify_timing(self.cal,"2026-11-25","2026-12-02",s,e),
                         "SETTLED_ARITHMETIC_ONLY")
        for changed in (dict(e,entry_date="2026-11-26"),
                        dict(e,exit_date="2026-12-01"),
                        dict(e,recorded_at_utc="2026-12-02T21:30:00Z"),
                        dict(e,net_return_by_cost_bp={"20":.03,"40":.026,"80":.022})):
            with self.assertRaises(ValueError):
                verify_timing(self.cal,"2026-11-25","2026-12-02",s,changed)
        with self.assertRaisesRegex(ValueError,"FIRST_CAPTURE_OUTSIDE_WINDOW"):
            verify_timing(self.cal,"2026-11-25","2026-11-27",
                          {"recorded_at_utc":"2026-11-27T14:30:00Z"},None)

    def test_immutable_ancestry(self):
        a={n:b"old\n" for n in JOURNALS.values()}
        a[PREFIX+"2026-11-23.json"]=b"first"
        b={n:v+b"new\n" for n,v in a.items() if n in JOURNALS.values()}
        b[PREFIX+"2026-11-23.json"]=b"first"
        verify_ancestry(a,b)
        with self.assertRaisesRegex(ValueError,"JOURNAL_ANCHOR_PREFIX_CHANGED"):
            verify_ancestry(a,dict(b,**{JOURNALS["BULL"]:b"changed"}))
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SNAPSHOT_CHANGED"):
            verify_ancestry(a,dict(b,**{PREFIX+"2026-11-23.json":b"changed"}))

    def test_outer_and_member_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"x.zip"
            m={"format":"kalman-daily20-drive-v1","research_only":True,
               "production_writes":False,"oos_score_count":20,
               "payload_hashes_sha256":{"x.json":sha(b"ok")}}
            with ZipFile(p,"w") as z:
                z.writestr("drive_manifest.json",json.dumps(m));z.writestr("x.json",b"ok")
            pin=sha(p.read_bytes())
            _,_,v=verified_zip(p,pin)
            self.assertEqual(v,{"x.json":b"ok"})
            with self.assertRaisesRegex(ValueError,"OUTER_SHA_MISMATCH"):
                verified_zip(p,"0"*64)
            with ZipFile(p,"w") as z:
                z.writestr("drive_manifest.json",json.dumps(m));z.writestr("x.json",b"changed")
            with self.assertRaisesRegex(ValueError,"MEMBER_SHA_MISMATCH"):
                verified_zip(p,sha(p.read_bytes()))


if __name__=="__main__":
    unittest.main()
