#!/usr/bin/env python3
"""Dashboard freshness banner must never confuse rendered time and source time."""
import datetime as dt
import unittest
from native_dashboard_cli import KST, source_status_notice

HEADER=["Entity","Source Received KST","Ingest Checked KST","Rows",
        "Unique IDs","Duplicate IDs","Missing IDs","Content SHA256",
        "State","Source Kind"]

def audit(received="2026-11-07 17:00:07 KST"):
    return [HEADER]+[[name,received,"2026-11-08 02:48:03 KST","200","100",
                      "100","0","a"*64,"PRESERVED_NO_NEW_REPORT","QQ IMAP"]
                      for name in ("Leads","Opportunities","Quotation")]

class DashboardSourceNoticeTests(unittest.TestCase):
    def test_sunday_dashboard_shows_saturday_asof_not_live(self):
        now=dt.datetime(2026,11,8,10,17,tzinfo=KST)
        note,age=source_status_notice(audit(),now)
        self.assertGreater(age,1000)
        self.assertIn("11/07 17:00",note)
        self.assertIn("11/08",note)
        self.assertIn("수신 지연",note)
        self.assertIn("화면 갱신",note)
        self.assertNotIn("최신화 완료",note)

    def test_same_day_recent_report_is_clearly_time_bounded(self):
        now=dt.datetime(2026,11,7,17,40,tzinfo=KST)
        note,age=source_status_notice(audit(),now)
        self.assertEqual(age,39)
        self.assertIn("최근 수신본",note)
        self.assertIn("11/07 17:00",note)

    def test_missing_entity_does_not_show_misleading_source(self):
        rows=audit()[:-1]
        with self.assertRaisesRegex(ValueError,"MISSING_ENTITY"):
            source_status_notice(rows,dt.datetime(2026,11,8,10,17,tzinfo=KST))

    def test_bad_origin_rejected(self):
        rows=audit()
        rows[1][9]="UNVERIFIED_MAIL"
        with self.assertRaisesRegex(ValueError,"UNTRUSTED"):
            source_status_notice(rows,dt.datetime(2026,11,8,10,17,tzinfo=KST))

    def test_duplicate_entity_rejected(self):
        rows=audit()
        rows.append(rows[1][:])
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            source_status_notice(rows,dt.datetime(2026,11,8,10,17,tzinfo=KST))

if __name__=="__main__":
    unittest.main()
