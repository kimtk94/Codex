import tempfile
import unittest
from pathlib import Path
from automation_policy.research_evidence import validate_manifest, verify

def fixture():
    return {"schema_version": 1, "kind": "ckd_stage_qc", "project": "CKD",
            "source_commit": "a"*40, "input_sha256": "b"*64, "synthetic": False,
            "qc_metrics": {"sample_count": 100}, "checks": [{"name":"sample_count_positive","passed":True}]}

class ResearchEvidenceTests(unittest.TestCase):
    def test_structural_pass_not_scientific_claim(self):
        result = validate_manifest(fixture())
        self.assertTrue(result["verified_manifest"])
        self.assertIn("scientific_validity", result["not_verified"])

    def test_fake_or_unmarked_evidence_denied(self):
        for value in (True,None):
            case = fixture()
            case["synthetic"] = value
            with self.assertRaises(ValueError):
                validate_manifest(case)

    def test_failed_check_denied(self):
        case = fixture()
        case["checks"][0]["passed"] = False
        with self.assertRaises(ValueError):
            validate_manifest(case)

    def test_missing_metrics_denied(self):
        case = fixture()
        case["qc_metrics"] = {}
        with self.assertRaises(ValueError):
            validate_manifest(case)

    def test_invalid_hash_denied(self):
        case = fixture()
        case["input_sha256"] = "INVALID"
        with self.assertRaises(ValueError):
            validate_manifest(case)
