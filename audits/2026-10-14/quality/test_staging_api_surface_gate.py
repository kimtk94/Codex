"""Synthetic static Staging endpoint security preflight, never a deployment."""
import copy
import json
import unittest
from staging_api_surface_gate import (
    EXPECTED_NAMES,SENSITIVE_API_PATHS,SNAPSHOT,scan_source,stage_decision
)


def mock_bundle():
    files={p:b"// static fixture" for p in EXPECTED_NAMES}
    files["api/assets.js"]=(
       b"module.exports=async function(req,res){"
       b"if(req.method!=='GET')return res.status(405).end();"
       b"return res.json({version:'fixture'});}"
    )
    files["api/ingest/etf.js"]=(
       b"module.exports=(req,res)=>{"
       b"if(req.method==='POST'){return sql`INSERT INTO sample_table VALUES (1)`}}"
    )
    files["api/position-ledger-tick.js"]=(
       b"const token=process.env.STAGING_DEMO_FLAG;"
       b"if(request.method==='POST'){sql`UPDATE dummy_table SET x=1`}"
    )
    return files


class StagingSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.source=scan_source(mock_bundle())
        self.snapshot=json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    def test_12_generated_api_paths_scanned(self):
        self.assertEqual(self.source["route_count"],12)
        self.assertEqual({x["file"] for x in self.source["routes"]},
                         {p for p in EXPECTED_NAMES if p.startswith("api/")})

    def test_six_routes_require_review_by_classification(self):
        self.assertEqual(self.source["sensitive_route_count"],len(SENSITIVE_API_PATHS))
        self.assertEqual(len(SENSITIVE_API_PATHS),6)

    def test_static_scan_detects_http_write_verbs_and_db_markers(self):
        self.assertIn("/api/ingest/etf",self.source["mutating_sql_marker_routes"])
        self.assertIn("/api/ingest/etf",self.source["http_write_verb_marker_routes"])
        self.assertIn("/api/position-ledger-tick",self.source["mutating_sql_marker_routes"])

    def test_reports_environment_variable_names_never_values(self):
        row=next(x for x in self.source["routes"] if x["route"]=="/api/position-ledger-tick")
        self.assertEqual(row["references_environment_variable_names"],
                         ["STAGING_DEMO_FLAG"])
        self.assertNotIn("production-token",repr(self.source))

    def test_actual_staging_snapshot_is_hold_due_to_missing_access_control(self):
        self.assertIs(self.snapshot["staging_sso_enabled"],False)
        self.assertIs(self.snapshot["staging_password_protection_enabled"],False)
        self.assertEqual(self.snapshot["staging_trusted_ip_rule_count"],0)
        result=stage_decision(self.snapshot,self.source)
        self.assertEqual(result["verdict"],"STAGING_RELEASE_HOLD")
        self.assertEqual(result["reason"],"STAGING_AUTH_PROTECTION_MISSING")

    def test_auth_protection_alone_insufficient(self):
        s={**self.snapshot,"staging_sso_enabled":True}
        self.assertEqual(stage_decision(s,self.source)["reason"],
                         "STAGING_CREDENTIAL_ISOLATION_MISSING")

    def test_isolated_credentials_alone_insufficient(self):
        s={**self.snapshot,"staging_sso_enabled":True,
           "staging_credentials_isolated_verified":True}
        self.assertEqual(stage_decision(s,self.source)["reason"],
                         "STAGING_DATABASE_ISOLATION_MISSING")

    def test_runtime_access_and_sensitive_auth_review_required(self):
        s={**self.snapshot,"staging_sso_enabled":True,
           "staging_credentials_isolated_verified":True,
           "staging_database_isolation_verified":True}
        self.assertEqual(stage_decision(s,self.source)["reason"],
                         "STAGING_ACCESS_CONTROL_UNVERIFIED")
        s["staging_runtime_api_access_verified"]=True
        self.assertEqual(stage_decision(s,self.source)["reason"],
                         "STAGING_SENSITIVE_API_REVIEW_INCOMPLETE")

    def test_explicit_approval_is_separate_requirement(self):
        s={**self.snapshot,"staging_sso_enabled":True,
           "staging_credentials_isolated_verified":True,
           "staging_database_isolation_verified":True,
           "staging_runtime_api_access_verified":True,
           "staging_endpoint_auth_review_complete":True}
        self.assertEqual(stage_decision(s,self.source)["reason"],"OPERATOR_APPROVAL_MISSING")
        s["staging_operator_approved"]=True
        r=stage_decision(s,self.source)
        self.assertEqual(r["verdict"],"READY_FOR_SEPARATE_OPERATOR_REVIEW")
        self.assertFalse(r["can_deploy"])

    def test_incomplete_manifest_fails_closed(self):
        bundle=mock_bundle()
        del bundle["api/health.js"]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_30_FILE_BUNDLE"):
            scan_source(bundle)

    def test_wrong_staging_project_is_rejected(self):
        s={**self.snapshot,"staging_project_id":"prj_wrong"}
        self.assertEqual(stage_decision(s,self.source)["reason"],"INCORRECT_STAGING_TARGET")

    def test_snapshot_contains_no_real_secret_values(self):
        raw=SNAPSHOT.read_text(encoding="utf-8").lower()
        for word in ("sk-proj-","bearer ","refresh_token","password_value","client_secret"):
            self.assertNotIn(word,raw)

if __name__=="__main__":
    unittest.main()
