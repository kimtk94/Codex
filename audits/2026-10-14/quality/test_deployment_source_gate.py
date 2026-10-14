"""Synthetic and sanitized evidence tests; no Vercel network/credentials."""
import json
from pathlib import Path
import unittest
from deployment_source_gate import deployment_source_gate as gate

SNAPSHOT = Path(__file__).resolve().parents[2] / "2026-10-15" / "vercel_link_attestation_snapshot.json"


class DeploymentSourceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=json.loads(SNAPSHOT.read_text())

    def test_actual_connected_vercel_metadata_blocks_release(self):
        r=gate(self.snapshot)
        self.assertEqual(r["verdict"],"RELEASE_HOLD")
        self.assertEqual(r["reason"],"LINKED_REPOSITORY_MISMATCH")
        self.assertFalse(r["can_deploy"])

    def test_correct_project_wrong_repo_fails(self):
        d={**self.snapshot, "linked_source_repository":"unknown/repo"}
        self.assertEqual(gate(d)["reason"],"LINKED_REPOSITORY_MISMATCH")

    def test_corrected_link_only_not_enough(self):
        d={**self.snapshot, "linked_source_repository":"kimtk94/Codex"}
        self.assertEqual(gate(d)["reason"],"DEPLOYED_REPOSITORY_MISMATCH")

    def test_matching_repo_but_missing_runtime_attestation_fails(self):
        d={**self.snapshot,
           "linked_source_repository":"kimtk94/Codex",
           "production_deployment_source_repository":"kimtk94/Codex"}
        self.assertEqual(gate(d)["reason"],"DEPLOYED_RUNTIME_JS_UNVERIFIED")

    def test_source_fully_attested_does_not_approve_deploy(self):
        d={**self.snapshot,
           "linked_source_repository":"kimtk94/Codex",
           "production_deployment_source_repository":"kimtk94/Codex",
           "runtime_js_attested":True}
        x=gate(d)
        self.assertEqual(x["verdict"],"SOURCE_ATTESTATION_PASS")
        self.assertFalse(x["can_deploy"])

    def test_wrong_project_id(self):
        d={**self.snapshot,"project_id":"prj_not_authentic"}
        self.assertEqual(gate(d)["reason"],"PROJECT_ID_MISMATCH")

    def test_invalid_git_sha(self):
        d={**self.snapshot,"linked_source_repository":"kimtk94/Codex",
           "production_deployment_source_repository":"kimtk94/Codex",
           "production_deployment_commit":"abc"}
        self.assertEqual(gate(d)["reason"],"DEPLOYED_COMMIT_UNVERIFIED")

    def test_wrong_target_alias(self):
        d={**self.snapshot,"linked_source_repository":"kimtk94/Codex",
           "production_deployment_source_repository":"kimtk94/Codex",
           "production_alias":"untrusted.example.com"}
        self.assertEqual(gate(d)["reason"],"PRODUCTION_ALIAS_UNVERIFIED")

    def test_missing_fields_fail_closed(self):
        self.assertEqual(gate({})["verdict"],"RELEASE_HOLD")

    def test_not_exposing_runtime_identifiers_in_gate_output(self):
        r=gate(self.snapshot)
        self.assertNotIn("2615e63e3b3",str(r))
        self.assertNotIn("IS_Analysis_V3",str(r))


if __name__ == "__main__":
    unittest.main()
