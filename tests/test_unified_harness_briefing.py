import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.unified_harness_briefing import load, report, clean

class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.now=dt.datetime(2026,10,18,tzinfo=dt.timezone.utc)
    def tearDown(self): self.tmp.cleanup()
    def write(self,domain="is_ckd",**kw):
        data={"domain":domain,"status":"COMPLETE","summary":"Verified audit",
              "next_action":"No action","requires_approval":False,
              "evidence":["test-safe"],"observed_at":self.now.isoformat()}
        data.update(kw)
        (self.folder/(domain+".json")).write_text(json.dumps(data))
    def test_missing_all_unknown(self):
        out=report(self.folder,self.now)
        self.assertEqual(out.count("— UNKNOWN"),4)
    def test_fresh_valid(self):
        self.write()
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"COMPLETE")
    def test_stale_unknown(self):
        self.write(observed_at=(self.now-dt.timedelta(days=2)).isoformat())
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"UNKNOWN")
    def test_future_unknown(self):
        self.write(observed_at=(self.now+dt.timedelta(hours=1)).isoformat())
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"UNKNOWN")
    def test_wrong_domain_unknown(self):
        self.write(domain="css")
        (self.folder/"is_ckd.json").write_bytes((self.folder/"css.json").read_bytes())
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"UNKNOWN")
    def test_approval_queue(self):
        self.write(status="REVIEW_REQUIRED",requires_approval=True,next_action="Check interpretation")
        out=report(self.folder,self.now)
        self.assertIn("is_ckd: Check interpretation",out)
    def test_redacts_obvious_secrets(self):
        self.assertNotIn("supersecret",clean("token=supersecret"))
        self.assertNotIn("supersecret",clean("Bearer supersecret"))
    def test_invalid_approval_type_unknown(self):
        self.write(requires_approval="no")
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"UNKNOWN")
    def test_symlink_unknown(self):
        target=self.folder/"elsewhere.json"
        target.write_text("{}")
        (self.folder/"is_ckd.json").symlink_to(target)
        self.assertEqual(load(self.folder,"is_ckd",self.now)["status"],"UNKNOWN")

if __name__=="__main__":
    unittest.main()
