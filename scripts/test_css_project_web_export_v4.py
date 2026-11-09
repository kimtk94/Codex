import datetime as dt
import unittest
from css_project_web_export_v4 import build_snapshot, KST, ALLOWED_STATUS

NOW = dt.datetime(2026,11,9,12,0,tzinfo=KST)
HEAD = ["Project / Sub-project","AMEA","Institution","Customer","Service",
        "Feishu Status (latest)","CSS Stage (legacy)","CSS Progress %",
        "CSS Last Email","Sample Count","Feishu Remaining TAT Days",
        "Feishu Expected Completion","Expected Revenue Month",
        "Manual Month Override (reference)","Invoice Count",
        "Invoice Actual KRW","Billing Classification"]
ROW = ["X209SC26106973-Z01","AMEA2026102103","Example Univ.","Private Customer",
       "mRNA-Seq","Waiting Sequencing","Sample QC","60","2026-10-20","12",
       "15","2026-12-11","2026-12","","0","0","NOT_INVOICED"]
MANIFEST = [["Source","Source Date","Synced At KST","Source ID","Rows"],
            ["Online-Project","2026-11-09","2026-11-09T10:55:33+09:00",
             "tblZGzTAZ7oPWL7L","110"]]
MAIL = [["Updated At KST","State"],["2026-11-09 10:58:16 KST","WINDOW_CAUGHT_UP"]]

class WebExportTests(unittest.TestCase):
    def test_strict_projection_excludes_customer(self):
        table, report = build_snapshot([HEAD,ROW], MANIFEST, MAIL, NOW)
        self.assertEqual(report["source_project_count"],1)
        self.assertEqual(table[2][0],"X209SC26106973-Z01")
        self.assertEqual(table[2][4],"Waiting Sequencing")
        self.assertEqual(table[2][-2], ALLOWED_STATUS)
        self.assertNotIn("Private Customer", str(table))
        self.assertFalse(report["original_feishu_authenticated"])
        self.assertFalse(report["financial_actual_certified"])
    def test_duplicate_project_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            build_snapshot([HEAD,ROW,ROW], MANIFEST, MAIL, NOW)
    def test_invalid_missing_id(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            build_snapshot([HEAD,[""] + ROW[1:]],MANIFEST,MAIL,NOW)
    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            build_snapshot([HEAD,ROW],[],MAIL,NOW)
    def test_old_sync_rejected(self):
        old=[MANIFEST[0],["Online-Project","2026-10-01",
                           "2026-10-01T00:00:00+09:00","ID","110"]]
        with self.assertRaisesRegex(ValueError,"STALE"):
            build_snapshot([HEAD,ROW],old,MAIL,NOW)
    def test_stale_mail_rejected(self):
        with self.assertRaisesRegex(ValueError,"STALE"):
            build_snapshot([HEAD,ROW],MANIFEST,[MAIL[0],
                ["2026-10-01 10:58:16 KST","WINDOW_CAUGHT_UP"]],NOW)
    def test_size_and_schema_enforced(self):
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            build_snapshot([HEAD[:4],ROW],MANIFEST,MAIL,NOW)
    def test_no_new_data_not_invented(self):
        table, r=build_snapshot([HEAD,ROW],MANIFEST,MAIL,NOW)
        self.assertNotEqual(r["status"],"NO_NEW_DATA")
        self.assertIn("MIRROR",r["status"])

if __name__ == "__main__":
    unittest.main()
