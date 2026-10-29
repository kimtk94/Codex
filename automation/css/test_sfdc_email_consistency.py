"""Offline parity regressions: independent NONE placeholders must not hide reviewer decisions."""
import contextlib
import io
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).parent
MODULE=ROOT/"sfdc_email_consistency_check.py"
SFDC="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QQ="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"

def mail(uid):
    return ["","","","","","","","",uid]

def decision(action,uid):
    return [action,"","","",uid]

class FakeValues:
    def __init__(self,sfm,qqm,sfd,qqd):
        self.data={
            (QQ,"BI Unanswered Triage"): [[""]*8+["Thread UID"]]+qqm,
            (SFDC,"Unanswered Emails"): [[""]*8+["Thread UID"]]+sfm,
            (QQ,"BI Mail Review & Exclusions"): [[""]*4+["Mail UID (Key)"]]+qqd,
            (SFDC,"Email Review Decisions"): [[""]*4+["Mail UID (Key)"]]+sfd,
        }
    def get(self,**kwargs):
        a1=kwargs["range"]
        tab=a1.split("'")[1]
        values=self.data[(kwargs["spreadsheetId"],tab)]
        return types.SimpleNamespace(execute=lambda:{"values":values})

def load_main(fake):
    names=("google","google.oauth2","google.oauth2.service_account",
           "googleapiclient","googleapiclient.discovery")
    old={name:sys.modules.get(name) for name in names}
    modules={name:types.ModuleType(name) for name in names}
    class Credentials:
        @staticmethod
        def from_service_account_info(*args,**kwargs):
            return object()
    modules["google.oauth2.service_account"].Credentials=Credentials
    modules["googleapiclient.discovery"].build=lambda *a,**k:types.SimpleNamespace(
        spreadsheets=lambda:types.SimpleNamespace(values=lambda:fake))
    sys.modules.update(modules)
    try:
        namespace={"__name__":"offline_test"}
        exec(compile(MODULE.read_text(encoding="utf-8"),str(MODULE),"exec"),namespace)
        return namespace["main"]
    finally:
        for name,val in old.items():
            if val is None:
                sys.modules.pop(name,None)
            else:
                sys.modules[name]=val

class ParityTest(unittest.TestCase):
    def case(self,sfd,qqd,sfm=None,qqm=None):
        sfm=[mail("inbox:1")] if sfm is None else sfm
        qqm=[mail("inbox:1")] if qqm is None else qqm
        main=load_main(FakeValues(sfm,qqm,sfd,qqd))
        output=io.StringIO()
        with patch.dict("os.environ",{"GOOGLE_SERVICE_ACCOUNT_JSON":"{}"}):
            with contextlib.redirect_stdout(output):
                main()
        return json.loads(output.getvalue().strip())
    def test_placeholder_only_qq_is_permitted(self):
        result=self.case([decision("EXCLUDE_MAIL","inbox:1")],
                         [decision("EXCLUDE_MAIL","inbox:1"),
                          decision("NONE","inbox:3"),
                          decision("NONE","inbox:4"),
                          decision("NONE","inbox:5")])
        self.assertEqual(result["consistency"],"PASS")
        self.assertEqual(result["active_decisions"],1)
        self.assertEqual(result["qq_placeholder_only"],3)
    def test_placeholder_only_sf_is_permitted(self):
        result=self.case([decision("NONE","inbox:2")],[])
        self.assertEqual(result["sfdc_placeholder_only"],1)
    def test_action_disagreement_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Explicit decision"):
            self.case([decision("EXCLUDE_MAIL","inbox:1")],
                      [decision("RESTORE_MAIL","inbox:1")])
    def test_action_missing_from_one_side_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Explicit decision"):
            self.case([decision("NONE","inbox:1")],
                      [decision("EXCLUDE_SENDER","inbox:1")])
    def test_duplicate_decision_uid_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Duplicate decision UID"):
            self.case([decision("NONE","inbox:1"),decision("NONE","inbox:1")],[])
    def test_unknown_reviewer_action_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"Unexpected reviewer decision"):
            self.case([decision("DELETE_ALL","inbox:1")],[])
    def test_differing_mail_snapshots_still_fail(self):
        with self.assertRaisesRegex(RuntimeError,"Email UIDs differ"):
            self.case([],[],sfm=[mail("inbox:1")],qqm=[mail("inbox:2")])
    def test_empty_mail_snapshot_still_fails(self):
        with self.assertRaisesRegex(RuntimeError,"Empty mail snapshot"):
            self.case([],[],sfm=[],qqm=[])

if __name__=="__main__":
    unittest.main()
