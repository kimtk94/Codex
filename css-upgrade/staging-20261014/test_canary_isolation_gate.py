"""Regression tests for canary isolation tripwires (synthetic input only)."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from canary_isolation_gate import (
    AllowlistedSheetsClient,
    CanaryPolicy,
    IsolationViolation,
    NoOutbound,
    audit_import_time_calls,
    refuse_unsafe_import,
    run_full_main,
)


class FakeSheet:
    def __init__(self):
        self.calls = []

    def worksheet(self, tab):
        self.calls.append(tab)
        return {"tab": tab}


class FakeClient:
    def __init__(self):
        self.opened = []
        self.sheet = FakeSheet()

    def open_by_key(self, key):
        self.opened.append(key)
        return self.sheet


class IsolationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="css-gate-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        project = self.root / "project.sqlite3"
        mail = self.root / "mail.sqlite3"
        for p in (project, mail):
            with sqlite3.connect(p) as con:
                con.execute("CREATE TABLE synthetic(value INTEGER)")
                con.execute("INSERT INTO synthetic VALUES (1)")
        for d in ("backups", "logs", "output"):
            (self.root / d).mkdir()
        self.policy = CanaryPolicy(
            root=self.root,
            canary_sheet_id="synthetic-canary",
            forbidden_sheet_ids=frozenset({"production-token", "another-production"}),
            paths={
                "project_db":project, "mail_db":mail,
                "backup_dir":self.root/"backups", "log_dir":self.root/"logs",
                "output_dir":self.root/"output",
            },
            allowed_tabs=frozenset({"SIF Skip History", "Manual Override QA"}),
            network_mail_disabled=True,
            external_drive_writes_disabled=True,
            salesforce_writes_disabled=True,
        )

    def test_valid_fixture(self):
        self.policy.validate()
        self.assertTrue(self.policy.allow_sheet("synthetic-canary"))

    def test_production_id_is_denied(self):
        client=AllowlistedSheetsClient(FakeClient(),self.policy)
        with self.assertRaises(IsolationViolation):
            client.open_by_key("production-token")
        self.assertEqual(client._raw.opened, [])

    def test_alternate_spreadsheet_open_is_denied(self):
        client=AllowlistedSheetsClient(FakeClient(),self.policy)
        with self.assertRaises(IsolationViolation):
            client.open("production")
        with self.assertRaises(IsolationViolation):
            client.open_by_url("https://docs.google.com/anything")

    def test_allowlisted_sheet_and_tab(self):
        fake=FakeClient()
        sheet=AllowlistedSheetsClient(fake,self.policy).open_by_key("synthetic-canary")
        self.assertEqual(sheet.worksheet("SIF Skip History"),{"tab":"SIF Skip History"})
        with self.assertRaises(IsolationViolation):
            sheet.worksheet("CSS Project Dashboard")
        with self.assertRaises(IsolationViolation):
            sheet.batch_update({"a":1})
        self.assertEqual(fake.opened,["synthetic-canary"])

    def test_flags_fail_closed(self):
        for field in ("network_mail_disabled","external_drive_writes_disabled",
                      "salesforce_writes_disabled"):
            with self.subTest(field=field):
                with self.assertRaises(IsolationViolation):
                    replace(self.policy,**{field:False}).validate()

    def test_missing_persistent_sink_is_denied(self):
        altered=dict(self.policy.paths)
        del altered["backup_dir"]
        with self.assertRaises(IsolationViolation):
            replace(self.policy,paths=altered).validate()

    def test_path_escape_denied(self):
        altered=dict(self.policy.paths)
        altered["output_dir"]=Path("/tmp/outside-this-canary")
        with self.assertRaises(IsolationViolation):
            replace(self.policy,paths=altered).validate()

    def test_symlink_escape_denied(self):
        out=self.root/"logs-link"
        out.symlink_to(Path("/tmp"))
        altered=dict(self.policy.paths)
        altered["log_dir"]=out
        with self.assertRaises(IsolationViolation):
            replace(self.policy,paths=altered).validate()

    def test_missing_db_denied(self):
        altered=dict(self.policy.paths)
        altered["project_db"]=self.root/"missing.sqlite3"
        with self.assertRaises(IsolationViolation):
            replace(self.policy,paths=altered).validate()

    def test_collision_denied(self):
        with self.assertRaises(IsolationViolation):
            replace(self.policy,canary_sheet_id="production-token").validate()

    def test_no_outbound_tripwire(self):
        for method in ("send","sendmail","create_draft","upload_file"):
            with self.assertRaises(IsolationViolation):
                getattr(NoOutbound(),method)

    def test_import_time_side_effects_are_detected(self):
        source="""import sqlite3
import subprocess
sqlite3.connect('sample.db')
subprocess.run(['pip','install','x'])
def helper():
    sqlite3.connect('ignored.db')
if __name__ == '__main__':
    sqlite3.connect('guarded.db')
"""
        self.assertEqual(
            audit_import_time_calls(source),("sqlite3.connect","subprocess.run")
        )
        with self.assertRaises(IsolationViolation):
            refuse_unsafe_import(source)

    def test_safe_import_check_only_parses(self):
        source="def helper():\n    print('never executed')\n"
        self.assertEqual(audit_import_time_calls(source),())
        refuse_unsafe_import(source)

    def test_full_main_always_blocked(self):
        with self.assertRaisesRegex(IsolationViolation,"FULL_MAIN_BLOCKED"):
            run_full_main()
        with self.assertRaisesRegex(IsolationViolation,"FULL_MAIN_BLOCKED"):
            run_full_main(self.policy)


if __name__=="__main__":
    unittest.main(verbosity=2)
