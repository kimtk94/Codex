"""Deterministic source-byte comparison tests; no network/deploy."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from active_bundle_fingerprint_audit import (
    digest_report, legacy_exposure_flags, audit, BASELINE_SNAPSHOT, KEY_FILES
)


def files(guarded=False):
    if guarded:
        app=b"function verifiedNet(x){} var net=verifiedNet(x)"
        api=b"NULL::numeric AS net_return, NULL::numeric AS round_trip_cost_bps"
    else:
        app=b"var gross=n(x.realized_return_pct),net=n(x.net_return)"
        api=b"realized_return_pct,net_return,round_trip_cost_bps"
    return {"app.js":app,"api/assets.js":api,
            "api/health.js":b"health", "index.html":b"<html/>",
            "vercel.json":b"{}"}


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.legacy=files()
        self.guarded=files(True)
        self.live={p:hashlib.sha1(v).hexdigest() for p,v in self.legacy.items()}
        self.snapshot={"hosts":{"kalman-investment-hub-v2.vercel.app":{
            "deployment":"dpl_demo","files":self.live}}}

    def test_sha1_exact_match_is_content_identity_only(self):
        r=digest_report(self.live,self.legacy)
        self.assertEqual(set(r["matched_files"]),set(KEY_FILES))
        self.assertTrue(r["source_fingerprint_match"])
        self.assertTrue(r["app_and_api_identical"])

    def test_guarded_candidate_must_differ_from_known_legacy_file(self):
        r=digest_report(self.live,self.guarded)
        self.assertFalse(r["app_and_api_identical"])
        self.assertEqual(r["matched_files"],["api/health.js","index.html","vercel.json"])

    def test_legacy_code_exposure_flags(self):
        q=legacy_exposure_flags(self.legacy)
        self.assertTrue(q["legacy_direct_net_renderer"])
        self.assertTrue(q["legacy_raw_net_api_projection"])
        self.assertFalse(q["guarded_net_renderer"])
        self.assertFalse(q["guarded_net_api_projection"])

    def test_guarded_exposure_flags(self):
        q=legacy_exposure_flags(self.guarded)
        self.assertFalse(q["legacy_direct_net_renderer"])
        self.assertFalse(q["legacy_raw_net_api_projection"])
        self.assertTrue(q["guarded_net_renderer"])
        self.assertTrue(q["guarded_net_api_projection"])

    def test_baseline_match_cannot_authorize_release(self):
        with patch("active_bundle_fingerprint_audit._manifest",
                   side_effect=lambda root,version: self.guarded if root == Path("/audit") else self.legacy):
            r=audit(Path("/main"),Path("/audit"),self.snapshot)
        self.assertIn("v7.4.23",r["baseline_app_api_exact_versions"])
        self.assertFalse(r["audit_candidate_app_api_exact_active"])
        self.assertEqual(r["source_p1_status"],
                         "P1_ACTIVE_SOURCE_UNGUARDED_NET_RETURN")
        self.assertIn("v7.4.23",r["exact_unguarded_release_matches"])
        self.assertTrue(r["source_fingerprint_not_http_response"])
        self.assertFalse(r["runtime_http_attested"])
        self.assertFalse(r["release_authorized"])

    def test_bad_deployed_file_digest_refused(self):
        s=copy.deepcopy(self.snapshot)
        s["hosts"]["kalman-investment-hub-v2.vercel.app"]["files"]["app.js"]="not-a-sha1"
        with self.assertRaisesRegex(ValueError,"BAD_VERCEL_FILE_UID"):
            audit(Path("/main"),Path("/audit"),s)

    def test_actual_source_snapshot_contains_only_digests_not_api_responses(self):
        d=json.loads(BASELINE_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertIn("kalman-investment-hub-v2.vercel.app",d["hosts"])
        for x in d["hosts"].values():
            for digest in x["files"].values():
                self.assertEqual(len(digest),40)
                self.assertTrue(all(c in "0123456789abcdef" for c in digest))
        raw=BASELINE_SNAPSHOT.read_text(encoding="utf-8").lower()
        self.assertNotIn("bearer ",raw)
        self.assertNotIn("sk-proj-",raw)
        self.assertNotIn("refresh_token",raw)


if __name__=="__main__":
    unittest.main()
