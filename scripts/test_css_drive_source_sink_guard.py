"""Offline tests; never access Google."""
import datetime as dt
import unittest
from css_drive_source_sink_guard import classify, timestamp, UTC

NOW = dt.datetime(2026,11,9,3,0,tzinfo=UTC)
META = [["key","value"],["last_run_updated_at","2026-10-19T04:20:29+00:00"]]
WEB = [["WEB_EXPORT","2026. 11. 9 오전 11:03:32"],[],[],[],
       ["KPI","latest_project_email","2026-10-19 12:07"]]
HEALTH = [["run_id","version","status","started","finished"],
          ["r1","v1","SUCCESS","2026-10-19T03:20:00+00:00","2026-10-19T03:25:00+00:00"]]
MAIL = [["2026-11-09T10:53:22+09:00","a","b","c","project","AMEA2026091421"]]

class CSSDriveGuardTests(unittest.TestCase):
    def test_real_world_shape_lag(self):
        r=classify(META,WEB,HEALTH,MAIL,now=NOW)
        self.assertEqual(r["status"],"SINK_LAG")
        self.assertEqual(r["legacy_mail_collector_freshness"],"STALE")
        self.assertEqual(r["css_system_health_freshness"],"STALE")
        self.assertIsNone(r["confirmed_unreflected_count"])
    def test_aligned_recent_source_and_sink(self):
        web=[["WEB_EXPORT","2026. 11. 9 오전 11:03:32"],[],[],[],
             ["KPI","latest_project_email","2026-11-09 10:53"]]
        self.assertEqual(classify(META,web,HEALTH,MAIL,now=NOW)["status"],"PASS")
    def test_missing_source_or_sink_never_pass(self):
        self.assertEqual(classify(META,WEB,HEALTH,[],now=NOW)["status"],"SOURCE_UNAVAILABLE")
        self.assertEqual(classify(META,[["WEB_EXPORT"]],HEALTH,MAIL,now=NOW)["status"],"SOURCE_UNAVAILABLE")
    def test_old_source_is_stale(self):
        old=[["2026-10-19T12:07:00+09:00","","","","","AMEA2026091421"]]
        self.assertEqual(classify(META,WEB,HEALTH,old,now=NOW)["status"],"STALE")
    def test_timezone_and_nontext(self):
        self.assertEqual(timestamp("2026. 11. 9 오후 1:03:32"),
                         dt.datetime(2026,11,9,4,3,32,tzinfo=UTC))
        self.assertIsNone(timestamp("nonsense"))
        self.assertIsNone(timestamp("2026-11-09 10:50"))
    def test_private_data_not_emitted(self):
        raw=[["2026-11-09T10:53:22+09:00","private@example.org","","","secret","AMEA2026091421"]]
        report=str(classify(META,WEB,HEALTH,raw,now=NOW))
        self.assertNotIn("private@example.org",report)
        self.assertNotIn("AMEA2026091421",report)

if __name__=="__main__":
    unittest.main()
