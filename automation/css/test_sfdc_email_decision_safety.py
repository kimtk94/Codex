"""Behavioral regression tests; no network access or real sheet writes."""
import ast
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).parent

def load_main(fake_values):
    """Execute SFDC sync module with fake Google libraries."""
    names=("google","google.oauth2","google.oauth2.service_account",
           "googleapiclient","googleapiclient.discovery")
    previous={name:sys.modules.get(name) for name in names}
    modules={name:types.ModuleType(name) for name in names}
    class Credentials:
        @staticmethod
        def from_service_account_info(*args,**kwargs):
            return object()
    modules["google.oauth2.service_account"].Credentials=Credentials
    modules["googleapiclient.discovery"].build=lambda *a,**k:types.SimpleNamespace(
        spreadsheets=lambda:types.SimpleNamespace(values=lambda:fake_values))
    sys.modules.update(modules)
    namespace={"__name__":"unit_test"}
    try:
        exec(compile((ROOT/"sfdc_email_decision_sync.py").read_text(encoding="utf-8"),
                     "sfdc_email_decision_sync.py","exec"),namespace)
    finally:
        for name,value in previous.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value
    return namespace["main"]

class FakeValues:
    def __init__(self,sfdc,qq):
        self.sfdc=sfdc;self.qq=qq;self.writes=[];self.current=None
    def get(self,**kwargs):
        self.current=kwargs["range"]
        return self
    def execute(self):
        if self.current is not None:
            value=self.sfdc if "Email Review Decisions" in self.current else self.qq
            self.current=None
            return {"values":value}
        return {}
    def batchUpdate(self,**kw):
        self.writes.append(("update",kw))
        return self
    def append(self,**kw):
        self.writes.append(("append",kw))
        return self

def row(action,uid,status="NOT_SUBMITTED"):
    return [action,"customer@example.org","","",uid,"","",""+status,"",""]

class SyncBehaviorTest(unittest.TestCase):
    def execute_case(self,source,target,dry):
        fake=FakeValues(source,target)
        main=load_main(fake)
        with patch.dict("os.environ",{"GOOGLE_SERVICE_ACCOUNT_JSON":"{}",
                                     "DRY_RUN":"true" if dry else "false"}):
            main()
        return fake.writes
    def test_python_syntax(self):
        for name in ("sfdc_email_decision_sync.py","bi_mail_review_sync.py",
                     "sfdc_email_decision_ack.py","sfdc_sheets_preflight.py",
                     "sfdc_email_snapshot_refresh.py","sfdc_email_consistency_check.py",
                     "sfdc_email_sync_health.py"):
            with self.subTest(name=name):
                ast.parse((ROOT/name).read_text(encoding="utf-8"))
    def test_parity_rejects_empty_or_changed_headers(self):
        source=(ROOT/"sfdc_email_consistency_check.py").read_text(encoding="utf-8")
        self.assertIn("Empty mail snapshot cannot be certified PASS",source)
        self.assertIn("Unexpected mail snapshot column layout",source)
        self.assertIn("Unexpected decision column layout",source)
    def test_dry_run_never_writes(self):
        self.assertEqual(self.execute_case([row("EXCLUDE_MAIL","inbox:1")],[],True),[])
    def test_new_uid_enqueues_once(self):
        writes=self.execute_case([row("EXCLUDE_MAIL","inbox:1")],[],False)
        self.assertEqual([x[0] for x in writes],["append"])
        self.assertEqual(writes[0][1]["body"]["values"][0][4],"inbox:1")
    def test_synced_same_action_does_not_write(self):
        src=[row("EXCLUDE_MAIL","inbox:1")]
        qq=[row("EXCLUDE_MAIL","inbox:1","SYNCED:EXCLUDE_MAIL")]
        self.assertEqual(self.execute_case(src,qq,False),[])
    def test_conflict_fails_without_writes(self):
        fake=FakeValues([row("EXCLUDE_MAIL","inbox:1")],
                        [row("RESTORE_MAIL","inbox:1","NOT_SUBMITTED")])
        main=load_main(fake)
        with patch.dict("os.environ",{"GOOGLE_SERVICE_ACCOUNT_JSON":"{}","DRY_RUN":"false"}):
            with self.assertRaises(RuntimeError):main()
        self.assertEqual(fake.writes,[])
    def test_qq_restore_validation_precedes_write(self):
        source=(ROOT/"bi_mail_review_sync.py").read_text(encoding="utf-8")
        self.assertLess(source.index("    if problems:"),source.index("    batch(s,updates)"))
        self.assertIn('"restore_mail_not_found"',source)
        self.assertIn('"restore_sender_not_found"',source)

if __name__=="__main__":
    unittest.main()
