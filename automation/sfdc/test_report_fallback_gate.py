"""Offline SFDC backup freshness tests: no QQ/Google/CRM connections."""
import datetime as dt
import pathlib
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0,str(pathlib.Path(__file__).parent))
from report_fallback_gate import needs_backup,parse_kst_stamp,SOURCE_HEADER

KST=ZoneInfo("Asia/Seoul")
NOW=dt.datetime(2026,10,30,13,27,0,tzinfo=KST)

def grid(stamp="2026-10-30 12:40:00 KST"):
    return [SOURCE_HEADER.copy()]+[
        [v,"2026-10-30 12:00:00 KST",stamp,"500","500","0","0","abc",
         "STAGED_NOT_PROMOTED","QQ IMAP"]
        for v in ("Leads","Opportunities","Quotation")]

class BackupGateTests(unittest.TestCase):
    def test_recent_staged_triple_report_skips_redundant_backup(self):
        self.assertFalse(needs_backup(grid(),NOW))
    def test_old_staging_runs_backup_without_declaring_new_report(self):
        self.assertTrue(needs_backup(grid("2026-10-30 00:39:55 KST"),NOW))
    def test_one_old_entity_runs_recovery(self):
        rows=grid();rows[3][2]="2026-10-29 22:00:00 KST"
        self.assertTrue(needs_backup(rows,NOW))
    def test_source_not_staged_needs_recovery_but_not_source_acceptance(self):
        rows=grid();rows[2][8]="MISSING_ATTACHMENT"
        self.assertTrue(needs_backup(rows,NOW))
    def test_missing_or_duplicate_audit_row_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"ENTITY_MISSING"):
            needs_backup(grid()[:-1],NOW)
        rows=grid();rows.append(rows[1])
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            needs_backup(rows,NOW)
    def test_invalid_and_future_audit_timestamps_fail_closed(self):
        rows=grid();rows[1][2]="not a timestamp"
        with self.assertRaisesRegex(ValueError,"INVALID_AUDIT_TIMESTAMP"):
            needs_backup(rows,NOW)
        rows=grid("2026-10-31 13:27:00 KST")
        with self.assertRaisesRegex(ValueError,"IN_FUTURE"):
            needs_backup(rows,NOW)
    def test_malformed_header_and_naive_now_rejected(self):
        rows=grid();rows[0][2]="Wrong"
        with self.assertRaisesRegex(ValueError,"SCHEMA_CHANGED"):
            needs_backup(rows,NOW)
        with self.assertRaisesRegex(ValueError,"NOW_MUST_BE_TIMEZONE_AWARE"):
            needs_backup(grid(),NOW.replace(tzinfo=None))
    def test_kst_stamp_includes_tz(self):
        self.assertEqual(parse_kst_stamp("2026-10-30 12:40:00 KST").utcoffset(),dt.timedelta(hours=9))
    def test_workflow_backup_only_guard_and_pr_dry_run(self):
        source=(pathlib.Path(__file__).resolve().parents[2]/".github"/"workflows"/
                "sfdc-three-report-email-digestion.yml").read_text()
        self.assertIn("27 4 * * 1-5",source)
        self.assertIn("if: github.event_name == 'schedule' && github.event.schedule == '27 4 * * 1-5'",source)
        self.assertIn("steps.backup.outputs.refresh == 'true'",source)
        self.assertIn("github.event_name != 'pull_request'",source)
        self.assertIn("SFDC_REPORT_DRY_RUN:",source)

if __name__=="__main__":
    unittest.main()
