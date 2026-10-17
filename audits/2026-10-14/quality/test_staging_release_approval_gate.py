import copy
import json
import unittest
from staging_release_approval_gate import gate, EVIDENCE

class StagingReleaseApprovalTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=json.loads(EVIDENCE.read_text())
        self.proof={k:True for k in (
            "protected_alias_reverified","environment_variable_names_audited",
            "zero_production_credentials_attested","no_production_db_access_attested",
            "demo_only_30_file_digest_confirmed","api_handlers_disabled_confirmed",
            "separate_nonproduction_project_confirmed","rollback_target_captured",
            "operator_approved_staging_only")}
    def test_real_current_staging_is_held(self):
        self.assertEqual(gate(self.snapshot)["reason"],"STAGING_ACCESS_PROTECTION_MISSING")
    def test_wrong_project_rejected(self):
        s=dict(self.snapshot,staging_project_id="prj_wrong")
        self.assertEqual(gate(s,self.proof)["reason"],"WRONG_STAGING_PROJECT")
    def test_protection_alone_needs_independent_evidence(self):
        s=dict(self.snapshot,staging_sso_enabled=True)
        self.assertEqual(gate(s)["reason"],"INDEPENDENT_EVIDENCE_MISSING")
    def test_each_missing_attestation_fails(self):
        s=dict(self.snapshot,staging_sso_enabled=True)
        for k in self.proof:
            with self.subTest(k=k):
                p=copy.copy(self.proof);p[k]=False
                self.assertEqual(gate(s,p)["reason"],"MISSING_ATTESTATION:"+k)
    def test_hypothetical_full_attestation_is_not_deployment(self):
        s=dict(self.snapshot,staging_sso_enabled=True)
        v=gate(s,self.proof)
        self.assertEqual(v["status"],"PREFLIGHT_REVIEW_COMPLETE")
        self.assertFalse(v["deployment_authorized"])
    def test_password_protection_can_satisfy_gate_with_all_evidence(self):
        s=dict(self.snapshot,staging_password_protection_enabled=True)
        self.assertEqual(gate(s,self.proof)["status"],"PREFLIGHT_REVIEW_COMPLETE")
    def test_current_staging_is_not_approved_by_fake_attestation(self):
        self.assertEqual(gate(self.snapshot,self.proof)["status"],"STAGING_HOLD")
if __name__=="__main__":unittest.main()
