import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from evidence_review import TARGETS, VERIFIED, inspect_archive, compare

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.q, self.l = TARGETS
        self.n = 0

    def fixture(self, *, outage=None, tamper=None, missing=None, revision=None,
                anchors=None, identity=None, partial=False, duplicate=False):
        self.n += 1
        path = Path(self.temp.name) / f"{self.n}.zip"
        src = {}
        prefix = "research/issuer_ca_primary/"
        with zipfile.ZipFile(path, "w") as z:
            for sid, (claim,url,kind,_) in TARGETS.items():
                if partial and sid == self.l:
                    continue
                raw = (b"%PDF fixture" if kind == "pdf" else b"HTML fixture")
                if revision == sid:
                    raw += b" revised"
                rel = "raw/" + sid.lower() + "." + kind + ".gz"
                s = {"source_id":sid, "url":url, "status":"FETCHED_SOURCE_UNCERTIFIED",
                     "source_claim_independently_certified":False,
                     "body_sha256":hashlib.sha256(raw).hexdigest(),
                     "body_bytes":len(raw), "raw_archive":rel,
                     "anchor_grade_by_claim":{claim:"BOTH_NEARBY_ANCHORS_OBSERVED"}}
                if identity == sid:
                    s["url"] = "https://example.org/wrong"
                if anchors == sid:
                    s["anchor_grade_by_claim"] = {}
                if outage == sid:
                    s.update(status="HTTP_429_SOURCE_HOLD", body_sha256=None,
                             body_bytes=0, raw_archive=None, anchor_grade_by_claim={})
                elif missing != sid:
                    z.writestr(prefix+rel, gzip.compress(b"tampered" if tamper == sid else raw))
                src[sid] = s
            z.writestr(prefix+"report.json", json.dumps({"source_results":src}))
            if duplicate:
                z.writestr("elsewhere/issuer_ca_primary/report.json", "{}")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_verified_pair_still_hold(self):
        r = inspect_archive(*self.fixture())
        self.assertTrue(all(s["state"] == VERIFIED for s in r["sources"].values()))
        self.assertEqual(r["issuer_payments_certified"], 0)
        self.assertFalse(compare(r)["cache_reuse_authorized"])

    def test_wrong_external_pin(self):
        p, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, "ARCHIVE_PIN_MISMATCH"):
            inspect_archive(p, "0"*64)

    def test_missing_pin(self):
        p, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, "EXTERNAL_PIN_REQUIRED"):
            inspect_archive(p, "")

    def test_outage_candidate_not_authorization(self):
        prior = inspect_archive(*self.fixture())
        cur = inspect_archive(*self.fixture(outage=self.q))
        r = compare(cur, prior)
        self.assertEqual(r["decisions"][self.q], "PRIOR_PINNED_EVIDENCE_REVIEW_CANDIDATE_HOLD")
        self.assertFalse(r["cache_reuse_authorized"])
        self.assertEqual(r["source_finality_verified"], 0)

    def test_partial_prior_never_reused(self):
        prior = inspect_archive(*self.fixture(partial=True))
        cur = inspect_archive(*self.fixture(outage=self.q))
        self.assertEqual(compare(cur,prior)["decisions"][self.q], "NO_REUSE_HOLD")

    def test_tampering_not_fallback(self):
        prior = inspect_archive(*self.fixture())
        cur = inspect_archive(*self.fixture(tamper=self.q))
        self.assertEqual(cur["sources"][self.q]["state"], "SOURCE_BYTES_MISMATCH_HOLD")
        self.assertEqual(compare(cur,prior)["decisions"][self.q], "NO_REUSE_HOLD")

    def test_missing_raw_not_fallback(self):
        cur = inspect_archive(*self.fixture(missing=self.l))
        self.assertEqual(cur["sources"][self.l]["state"], "SOURCE_RAW_MISSING_HOLD")
        self.assertEqual(compare(cur)["decisions"][self.l], "NO_REUSE_HOLD")

    def test_changed_source_review(self):
        prior = inspect_archive(*self.fixture())
        cur = inspect_archive(*self.fixture(revision=self.l))
        self.assertEqual(compare(cur,prior)["decisions"][self.l], "SOURCE_REVISION_REVIEW_HOLD")

    def test_missing_anchors_not_fallback(self):
        prior = inspect_archive(*self.fixture())
        cur = inspect_archive(*self.fixture(anchors=self.l))
        self.assertEqual(compare(cur,prior)["decisions"][self.l], "NO_REUSE_HOLD")

    def test_wrong_identity(self):
        cur = inspect_archive(*self.fixture(identity=self.q))
        self.assertEqual(cur["sources"][self.q]["state"], "SOURCE_IDENTITY_MISMATCH_HOLD")

    def test_ambiguous_report(self):
        with self.assertRaisesRegex(ValueError, "REPORT_MISSING_OR_AMBIGUOUS"):
            inspect_archive(*self.fixture(duplicate=True))

if __name__ == "__main__":
    unittest.main()
