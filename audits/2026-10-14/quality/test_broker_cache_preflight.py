import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from broker_cache_preflight import token_preflight

class CachedTokenTests(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(token_preflight("/definitely/missing/cache.json",now=100)["status"],"BLOCKED")
    def test_valid_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"token.json"
            p.write_text(json.dumps({"access_token":"example-do-not-log","expires_at":1000}))
            before=p.read_bytes()
            value=token_preflight(p,now=100)
            self.assertEqual(value["status"],"READY")
            self.assertNotIn("access_token",str(value))
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(sorted(z.name for z in Path(tmp).iterdir()),["token.json"])
    def test_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"token.json"
            p.write_text(json.dumps({"access_token":"example","expires_at":150}))
            self.assertEqual(token_preflight(p,now=100)["reason"],"TOKEN_EXPIRED_OR_NEAR_EXPIRY")
    def test_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"token.json"
            p.write_text("invalid-json")
            self.assertEqual(token_preflight(p,now=100)["status"],"BLOCKED")
if __name__=="__main__":unittest.main()
