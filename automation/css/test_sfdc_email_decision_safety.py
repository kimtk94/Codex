"""Offline regression tests for SFDC decision conflict handling."""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).parent
class SyncSafetyTest(unittest.TestCase):
    def test_scripts_parse(self):
        for name in ("sfdc_email_decision_sync.py","bi_mail_review_sync.py",
                     "sfdc_email_decision_ack.py","sfdc_sheets_preflight.py"):
            with self.subTest(name=name):
                ast.parse((ROOT/name).read_text(encoding="utf-8"))
    def test_qq_blocks_invalid_restore_before_write(self):
        source=(ROOT/"bi_mail_review_sync.py").read_text(encoding="utf-8")
        self.assertIn('"restore_mail_not_found"',source)
        self.assertIn('"restore_sender_not_found"',source)
        self.assertLess(source.index('    if problems:'),source.index('    batch(s,updates)'))
    def test_uid_keyed_decisions_and_conflicts(self):
        source=(ROOT/"sfdc_email_decision_sync.py").read_text(encoding="utf-8")
        self.assertIn("by_uid=",source)
        self.assertIn("Conflicting unsynced reviewer actions",source)
        self.assertIn('if summary["dry_run"]:return',source)
    def test_ack_requires_qq_confirmed(self):
        source=(ROOT/"sfdc_email_decision_ack.py").read_text(encoding="utf-8")
        self.assertIn('expected="SYNCED:"+action',source)
        self.assertIn("field(original,7)==expected",source)
if __name__=="__main__":
    unittest.main()
