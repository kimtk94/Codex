"""Mocked, credential-free regressions for QQ -> SFDC mail-snapshot convergence."""
import contextlib
import io
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent
SCRIPT = ROOT / "sfdc_email_snapshot_refresh.py"

HEADER = ["Aging Days", "Triage Priority", "Sender Email", "Subject / Thread",
          "Received At", "Owner", "Project IDs", "Reply Evidence", "Thread UID",
          "Source Review", "Queue Class", "Excluded?", "Sender Exclusion",
          "Mail UID Exclusion", "CSS Sender Action", "Project Dashboard Exception",
          "Effective Queue", "Policy Reason", "Historical Thread Review",
          "Reviewer Mail Action", "Reviewer Sender Action"]
DHEADER = ["Decision (Edit)", "Sender Email", "Mail Received At (KST)",
           "Aging (Days)", "Mail UID (Key)", "Current Queue", "Reviewer Note (Edit)",
           "Decision Sync Status", "Snapshot Date", "Mail Subject / Thread"]

def mail(uid, subject="subject"):
    row = [""] * 21
    row[0], row[3], row[8], row[16] = "0", subject, uid, "MONITOR_0_1D"
    return row

def decision(uid, action):
    row = [""] * 10
    row[0], row[4], row[7] = action, uid, "NOT_SUBMITTED"
    return row

class Call:
    def __init__(self, op):
        self.op = op
    def execute(self):
        return self.op()

class FakeSheets:
    def __init__(self, qq_versions, current, decisions=None):
        self.qq_versions = qq_versions
        self.version = 0
        self.target = [HEADER[:]] + [r[:] for r in current]
        self.ledger = [DHEADER[:]] + [r[:] for r in (decisions or [])]
        self.write_count = 0
        self.append_count = 0
        self.clear_count = 0
    def spreadsheets(self):
        return types.SimpleNamespace(values=lambda: self)
    def get(self, **kw):
        book = kw["spreadsheetId"]
        area = kw["range"]
        tab = area.split("'")[1]
        def op():
            if tab == "BI Unanswered Triage":
                # Re-evaluate formula-backed QQ source after a target write.
                self.version = min(self.write_count, len(self.qq_versions)-1)
                data = [HEADER[:]] + self.qq_versions[self.version]
            elif tab == "Unanswered Emails":
                data = self.target
            elif tab == "Email Review Decisions":
                data = self.ledger
            else:
                raise AssertionError("Unexpected read: "+area)
            return {"values": [r[:] for r in data]}
        return Call(op)
    def update(self, **kw):
        area = kw["range"]
        tab = area.split("'")[1]
        data = kw["body"]["values"]
        def op():
            if tab == "Unanswered Emails":
                self.target = [HEADER[:]] + [r[:] for r in data]
                self.write_count += 1
            elif tab == "Email Review Decisions":
                for row in data:
                    if any(r[4] == row[4] for r in self.ledger[1:]):
                        raise AssertionError("Re-appended existing UID")
                    self.ledger.append(row[:])
                    self.append_count += 1
            else:
                raise AssertionError("Unexpected write: "+area)
            return {}
        return Call(op)
    def clear(self, **kw):
        self.clear_count += 1
        return Call(lambda: {})

def load(fake):
    names = ("google", "google.oauth2", "google.oauth2.service_account",
             "googleapiclient", "googleapiclient.discovery")
    previous = {name: sys.modules.get(name) for name in names}
    modules = {name: types.ModuleType(name) for name in names}
    class Credentials:
        @staticmethod
        def from_service_account_info(*args, **kwargs):
            return object()
    modules["google.oauth2.service_account"].Credentials = Credentials
    modules["googleapiclient.discovery"].build = lambda *args, **kw: fake
    sys.modules.update(modules)
    try:
        namespace = {"__name__": "offline_test"}
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), namespace)
        return namespace["main"]
    finally:
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

class SnapshotConvergenceTests(unittest.TestCase):
    def run_case(self, fake, dry=False):
        output = io.StringIO()
        main = load(fake)
        with patch.dict("os.environ", {
            "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
            "DRY_RUN": "true" if dry else "false",
        }):
            with contextlib.redirect_stdout(output):
                main()
        return output.getvalue()

    def test_stable_source_exact_copy_preserves_manual_decision(self):
        selected = decision("inbox:1", "EXCLUDE_MAIL")
        fake = FakeSheets(
            qq_versions=[[mail("inbox:2", "new customer"), mail("inbox:1", "older")]],
            current=[mail("inbox:1", "stale copy")],
            decisions=[selected])
        message = self.run_case(fake)
        self.assertIn("SOURCE_AND_TARGET_MATCH=true attempts=1", message)
        self.assertEqual([r[8] for r in fake.target[1:]], ["inbox:2", "inbox:1"])
        self.assertEqual(fake.ledger[1], selected)
        self.assertEqual(fake.append_count, 1)
        self.assertEqual(fake.ledger[-1][0], "NONE")

    def test_source_subject_whitespace_is_preserved(self):
        original = mail("inbox:2", "  Customer's exact subject  ")
        fake = FakeSheets(qq_versions=[[original]],current=[mail("inbox:1")])
        self.run_case(fake)
        self.assertEqual(fake.target[1][3], "  Customer's exact subject  ")

    def test_source_changes_mid_copy_retries_until_exact(self):
        fake = FakeSheets(
            qq_versions=[
                [mail("inbox:2"), mail("inbox:1")],
                [mail("inbox:3"), mail("inbox:2"), mail("inbox:1")],
            ],
            current=[mail("inbox:1")],
            decisions=[decision("inbox:1", "EXCLUDE_MAIL")])
        message = self.run_case(fake)
        self.assertIn("SOURCE_CHANGED_RETRY=1", message)
        self.assertIn("SOURCE_AND_TARGET_MATCH=true attempts=2", message)
        self.assertEqual([r[8] for r in fake.target[1:]], ["inbox:3", "inbox:2", "inbox:1"])
        self.assertEqual(fake.append_count, 2)
        self.assertEqual(fake.ledger[1][0], "EXCLUDE_MAIL")

    def test_changed_on_every_attempt_stays_failed_not_false_pass(self):
        fake = FakeSheets(
            qq_versions=[[mail("inbox:"+str(i))] for i in range(1, 5)],
            current=[mail("inbox:0")])
        with self.assertRaisesRegex(RuntimeError, "no PASS recorded"):
            self.run_case(fake)
        self.assertEqual(fake.write_count, 3)

    def test_duplicate_uid_refused_before_any_write(self):
        fake = FakeSheets(qq_versions=[[mail("inbox:1"), mail("inbox:1")]],current=[])
        with self.assertRaisesRegex(RuntimeError, "Duplicate QQ thread UIDs"):
            self.run_case(fake)
        self.assertEqual(fake.write_count, 0)

    def test_dry_run_does_not_write_anything(self):
        fake = FakeSheets(qq_versions=[[mail("inbox:2")]], current=[mail("inbox:1")])
        self.run_case(fake, dry=True)
        self.assertEqual(fake.write_count, 0)
        self.assertEqual(fake.append_count, 0)

    def test_empty_source_fails_closed(self):
        fake = FakeSheets(qq_versions=[[]],current=[mail("inbox:1")])
        with self.assertRaisesRegex(RuntimeError, "unexpectedly empty"):
            self.run_case(fake)

    def test_header_mismatch_fails_before_write(self):
        fake = FakeSheets(qq_versions=[[mail("inbox:2")]],current=[mail("inbox:1")])
        fake.target[0][3] = "Wrong header"
        with self.assertRaisesRegex(RuntimeError, "mail columns differ"):
            self.run_case(fake)
        self.assertEqual(fake.write_count, 0)

if __name__ == "__main__":
    unittest.main()
