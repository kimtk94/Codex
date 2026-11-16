import datetime as dt
import unittest
from css_projects_local import inspect, KST, HEAD, MARK
NOW=dt.datetime(2026,11,9,12,0,tzinfo=KST)
SRCH=["Project / Sub-project","AMEA","Institution","Customer","Service",
"Feishu Status (latest)","CSS Stage (legacy)","CSS Progress %",
"CSS Last Email","Sample Count","Feishu Remaining TAT Days",
"Feishu Expected Completion","Expected Revenue Month",
"Manual Month Override (reference)","Invoice Count","Invoice Actual KRW",
"Billing Classification"]
SOURCEROW=["X209SC26097688-Z01","AMEA2026091815","Example","Private Name","mRNA-Seq",
"Sequencing","Sample QC","90","2026-11-08","12","3","2026-11-14",
"2026-11","","1","2500000","BILLED"]
SINKROW=["X209SC26097688-Z01","AMEA2026091815","Example","mRNA-Seq",
"Sequencing","Sample QC","2026-11-08","12","2026-11-14","2026-11",
"1","BILLED",MARK,"2026-11-09"]
SINKMETA=["WEB_EXPORT_V4","MIRROR_ONLY","source_sheet","Sheet",
"feishu_source_date","2026-11-09","feishu_mirror_synced_at",
"2026-11-09T10:55:33+09:00","mail_mirror_updated_at",
"2026-11-09T10:58:16+09:00","sink_generated_at",
"2026-11-09T11:40:00+09:00","projects","1"]
MANIFEST=[["Source","Source Date","Synced At KST","Source ID","Rows"],
["Online-Project","2026-11-09","2026-11-09T10:55:33+09:00","id","110"]]
MAIL=[["Updated At KST","State"],["2026-11-09 10:58:16 KST","WINDOW_CAUGHT_UP"]]
def run(src=None,sink=None,manifest=None,mail=None,legacy_emails=None):
  return inspect(src if src is not None else [SRCH,SOURCEROW],
                 sink if sink is not None else [SINKMETA,HEAD,SINKROW],
                 manifest if manifest is not None else MANIFEST,
                 mail if mail is not None else MAIL,now=NOW,
                 legacy_emails=legacy_emails)
class Tests(unittest.TestCase):
  def test_parity(self):
    r=run()
    self.assertEqual(r["status"],"PASS_MIRROR_ONLY")
    self.assertEqual(r["source_count"],r["sink_count"])
    self.assertEqual(r["missing_project_count"],0)
    self.assertFalse(r["original_feishu_verified"])
    self.assertFalse(r["sfdc_save_verified"])
    self.assertNotIn("Private Name",str(r))
  def test_legacy_css_staleness_is_reported_separately_from_mirror_parity(self):
    legacy=[["latest_email_at"],["2026-10-19 12:07"],["2026-10-18 21:30"]]
    report=run(legacy_emails=legacy)
    self.assertEqual(report["status"],"PASS_MIRROR_ONLY")
    self.assertEqual(report["legacy_project_health"],"LEGACY_STALE")
    self.assertGreater(report["legacy_project_age_days"],7)
    self.assertIn("2026-10-19",report["legacy_project_latest_email_at"])
    self.assertFalse(report["original_feishu_verified"])
    self.assertFalse(report["original_qq_verified"])
  def test_legacy_recent_is_only_an_event_recency_not_original_proof(self):
    report=run(legacy_emails=[["latest_email_at"],["2026-11-08 10:00"]])
    self.assertEqual("LEGACY_EVENT_RECENT",report["legacy_project_health"])
    self.assertEqual("PASS_MIRROR_ONLY",report["status"])
    self.assertFalse(report["original_qq_verified"])
  def test_partial_mail_window_is_not_a_pass_even_with_fresh_mirror(self):
    changed=MAIL[1].copy();changed[1]="WINDOW_PARTIAL"
    result=run(mail=[MAIL[0],changed])
    self.assertEqual("PARTIAL_MIRROR",result["status"])
    self.assertEqual("WINDOW_PARTIAL",result["mail_window_state"])
    self.assertFalse(result["original_qq_verified"])
  def test_future_legacy_event_rejected_without_overriding_fresh_mirror(self):
    report=run(legacy_emails=[["latest_email_at"],["2026-12-20 12:07"]])
    self.assertEqual("LEGACY_NO_VALID_EVENT",report["legacy_project_health"])
    self.assertIsNone(report["legacy_project_latest_email_at"])
    self.assertEqual("PASS_MIRROR_ONLY",report["status"])
  def test_legacy_source_unavailable_is_not_same_as_no_event(self):
    self.assertEqual("NOT_CHECKED",run()["legacy_project_health"])
    self.assertEqual("LEGACY_NO_VALID_EVENT",run(legacy_emails=[])["legacy_project_health"])

  def test_mismatch(self):
    v=SINKROW.copy();v[4]="Wrong Status"
    self.assertEqual(run(sink=[SINKMETA,HEAD,v])["status"],"SINK_LAG")
  def test_missing_sink(self):
    self.assertEqual(run(sink=[SINKMETA,HEAD])["status"],"SINK_LAG")
  def test_old_mirror(self):
    changed=MANIFEST[1].copy();changed[2]="2026-10-01T10:55:33+09:00"
    self.assertEqual(run(manifest=[MANIFEST[0],changed])["status"],"STALE")
  def test_duplicate_id(self):
    with self.assertRaisesRegex(ValueError,"DUPLICATE"):
      run(src=[SRCH,SOURCEROW,SOURCEROW])
  def test_wrong_schema(self):
    with self.assertRaisesRegex(ValueError,"SINK_SCHEMA"):
      run(sink=[SINKMETA,["bad"]])
  def test_bad_mail_status(self):
    with self.assertRaisesRegex(ValueError,"MAIL_STATUS"):
      run(mail=[MAIL[0],["2026-11-09 10:58:16","WRONG"]])
if __name__=="__main__": unittest.main()
