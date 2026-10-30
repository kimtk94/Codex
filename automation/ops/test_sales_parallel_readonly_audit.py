"""No-credentials regression of preserved SFDC report evidence gate."""
import datetime as dt
import unittest
from sales_parallel_readonly_audit import verified_report_stage, KST

NOW=dt.datetime(2026,10,30,18,30,tzinfo=KST)

class ReportStageTests(unittest.TestCase):
    def record(self, state="PRESERVED_NO_NEW_REPORT"):
        return {"State":state,
                "Content SHA256":"a"*64,
                "Source Received KST":"2026-10-30 12:00:05 KST",
                "Ingest Checked KST":"2026-10-30 15:25:40 KST",
                "Rows":"493","Unique IDs":"493","Missing IDs":"0"}

    def test_preserved_and_new_staging_are_accepted(self):
        self.assertTrue(verified_report_stage(self.record(),NOW))
        self.assertTrue(verified_report_stage(self.record("STAGED_NOT_PROMOTED"),NOW))

    def test_missing_digest_or_unsupported_state_fails_closed(self):
        row=self.record();row["Content SHA256"]=""
        self.assertFalse(verified_report_stage(row,NOW))
        self.assertFalse(verified_report_stage(self.record("NO_VALID_REPORT_PRESERVED"),NOW))

    def test_stale_original_report_cannot_pass_fresh_ingest_timestamp(self):
        row=self.record();row["Source Received KST"]="2026-10-25 12:00:05 KST"
        self.assertFalse(verified_report_stage(row,NOW))

    def test_ids_and_missing_record_guard(self):
        row=self.record();row["Missing IDs"]="1"
        self.assertFalse(verified_report_stage(row,NOW))
        row=self.record();row["Unique IDs"]="494"
        self.assertFalse(verified_report_stage(row,NOW))

if __name__=="__main__":
    unittest.main()
