import json
import tempfile
import unittest
from pathlib import Path
from broker_audit_get import request_snapshot
class AuditGetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.cache=Path(self.tmp.name)/"token.json"
  self.cache.write_text(json.dumps({"access_token":"TEST_ONLY","expires_at":1000}))
 def tearDown(self): self.tmp.cleanup()
 def test_two_gets_no_cache_writes(self):
  before=self.cache.read_bytes(); calls=[]
  def fake(url,headers):
   calls.append(url); self.assertTrue(headers["Authorization"].startswith("Bearer ")); return {"result":[]}
  res=request_snapshot(self.cache,"test-account",transport=fake,now=100)
  self.assertEqual(res["status"],"OK")
  self.assertEqual(len(calls),2); self.assertEqual(before,self.cache.read_bytes())
  self.assertEqual([x.name for x in Path(self.tmp.name).iterdir()],["token.json"])
 def test_expiry_blocks(self):
  self.assertEqual(request_snapshot(self.cache,"acct",now=900)["status"],"BLOCKED")
 def test_401_no_retry(self):
  n=[]
  def denied(url,headers):
   n.append(url); raise RuntimeError("401")
  result=request_snapshot(self.cache,"acct",transport=denied,now=100)
  self.assertEqual(result["status"],"BLOCKED")
  self.assertEqual(len(n),1)
 def test_missing_account(self):
  self.assertEqual(request_snapshot(self.cache,"",now=100)["status"],"BLOCKED")
if __name__=="__main__":unittest.main()
