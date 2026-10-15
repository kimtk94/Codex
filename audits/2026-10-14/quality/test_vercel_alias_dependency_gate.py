"""Offline tests for real alias->deployment drift and shared API blast radius."""
import copy
import json
import unittest
from vercel_alias_dependency_gate import (
    MAIN, US, KR, STAGING, check_snapshot, compare_active_aliases,
    release_verdict, baseline_snapshot_path,
)


class AliasDependencyGateTests(unittest.TestCase):
    def setUp(self):
        self.base=json.loads(baseline_snapshot_path().read_text(encoding="utf-8"))

    def test_all_four_active_aliases_recorded(self):
        result=check_snapshot(self.base)
        self.assertEqual(result["status"],"BASELINE_VALIDATED")
        self.assertEqual(result["shared_api_clients"],[MAIN,US,KR])

    def test_main_alias_is_cli_not_research_git_deployment(self):
        main=self.base["domains"][MAIN]
        self.assertEqual(main["source"],"cli")
        self.assertNotEqual(main["alias_deployment_id"],
                            self.base["connected_main_git_deployment"]["id"])
        self.assertEqual(self.base["linked_repo"],"kimtk94/IS_Analysis_V3")

    def test_us_and_kr_rewrite_to_main_from_actual_config(self):
        for host in (US,KR):
            self.assertEqual(
                self.base["domains"][host]["api_rewrite"],
                "https://kalman-investment-hub-v2.vercel.app/api/:path*")

    def test_baseline_self_comparison_never_authorizes_release(self):
        result=compare_active_aliases(self.base,self.base)
        self.assertEqual(result["status"],"UNCHANGED")
        self.assertFalse(result["can_deploy"])

    def test_main_alias_drift_rechecks_all_three_sites(self):
        x=copy.deepcopy(self.base)
        x["domains"][MAIN]["alias_deployment_id"]="dpl_changed_main"
        r=compare_active_aliases(self.base,x)
        self.assertEqual(r["status"],"RECHECK_REQUIRED")
        self.assertEqual(r["downstream_impacted"],[MAIN,US,KR])
        self.assertIn({"site":MAIN,"field":"alias_deployment_id"},r["changed"])

    def test_us_alias_drift_does_not_claim_kr_api_changed(self):
        x=copy.deepcopy(self.base)
        x["domains"][US]["alias_deployment_id"]="dpl_changed_us"
        r=compare_active_aliases(self.base,x)
        self.assertEqual(r["status"],"RECHECK_REQUIRED")
        self.assertEqual(r["downstream_impacted"],[])

    def test_rewrite_to_unexpected_origin_blocks(self):
        x=copy.deepcopy(self.base)
        x["domains"][KR]["api_rewrite"]="https://other.example/api/:path*"
        self.assertEqual(check_snapshot(x)["reason"],"SHARED_API_REWRITE_CHANGED")
        self.assertEqual(compare_active_aliases(self.base,x)["status"],"HOLD")

    def test_domain_missing_fail_closed(self):
        x=copy.deepcopy(self.base)
        del x["domains"][STAGING]
        self.assertEqual(check_snapshot(x)["reason"],"CRITICAL_DOMAIN_SET_MISMATCH")

    def test_missing_main_api_source_blocked(self):
        x=copy.deepcopy(self.base)
        x["domains"][MAIN]["has_api_assets_file"]=False
        self.assertEqual(check_snapshot(x)["reason"],"MAIN_API_ASSETS_FILE_NOT_ATTESTED")

    def test_current_release_is_hold_due_to_wrong_git_link(self):
        r=release_verdict(self.base)
        self.assertEqual(r["verdict"],"PRODUCTION_HOLD")
        self.assertEqual(r["reason"],"MAIN_GIT_SOURCE_MISMATCH")
        self.assertEqual(r["affected_domains"],[MAIN,US,KR])

    def test_relink_alone_insufficient_without_actual_runtime_source(self):
        x=copy.deepcopy(self.base)
        x["linked_repo"]=x["intended_repo"]
        self.assertEqual(release_verdict(x)["reason"],"LIVE_BUNDLE_NOT_ATTESTED")

    def test_runtime_only_insufficient_without_smoke_tests(self):
        x=copy.deepcopy(self.base)
        x["linked_repo"]=x["intended_repo"]
        for site in x["domains"].values():
            site["full_runtime_js_attested"]=True
        self.assertEqual(release_verdict(x)["reason"],"CROSS_SITE_SMOKE_NOT_ATTESTED")

    def test_full_hypothetical_pass_still_requires_broker_and_approval(self):
        x=copy.deepcopy(self.base)
        x["linked_repo"]=x["intended_repo"]
        for site in x["domains"].values():
            site["full_runtime_js_attested"]=True
        checks=dict(read_only_endpoints_verified=True,
                    main_api_unverified_net_masked=True,
                    us_kr_downstream_smoke_pass=True,
                    rollback_alias_ids_verified=True,
                    source_sha_matched=True,
                    no_order_capability_enabled=True)
        self.assertEqual(release_verdict(x,live_checks=checks)["reason"],
                         "BROKER_OR_SERVER_PROVENANCE_MISSING")
        x.update(historical_p1_mirror_net_returns_corrected=True,
                 independent_broker_fee_provenance=True,
                 server_runtime_sha_verified=True)
        self.assertEqual(release_verdict(x,live_checks=checks)["reason"],
                         "OPERATOR_APPROVAL_MISSING")
        x["operator_approved_production_change"]=True
        r=release_verdict(x,live_checks=checks)
        self.assertEqual(r["verdict"],"PREFLIGHT_REVIEW_READY")
        self.assertFalse(r["release_authorized"])

    def test_snapshot_no_secrets_or_emails(self):
        raw=baseline_snapshot_path().read_text(encoding="utf-8").lower()
        for marker in ("password","secret","client_token","bearer ","sk-","@gmail"):
            self.assertNotIn(marker,raw)


if __name__=="__main__":
    unittest.main()
