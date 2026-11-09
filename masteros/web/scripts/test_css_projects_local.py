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
def run(src=None,sink=None,manifest=None,mail=None):
  return inspect(src if src is not None else [SRCH,SOURCEROW],
                 sink if sink is not None else [SINKMETA,HEAD,SINKROW],
                 manifest if manifest is not None else MANIFEST,
                 mail if mail is not None else MAIL,now=NOW)
class Tests(unittest.TestCase):
  def test_parity(self):
    r=run()
    self.assertEqual(r["status"],"PASS_MIRROR_ONLY")
    self.assertEqual(r["source_count"],r["sink_count"])
    self.assertEqual(r["missing_project_count"],0)
    self.assertFalse(r["original_feishu_verified"])
    self.assertFalse(r["sfdc_save_verified"])
    self.assertNotIn("Private Name",str(r))
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
