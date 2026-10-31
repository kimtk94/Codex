"""P0 CI orchestration policy tests. No credentials or network."""
import importlib.util
import os
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parent

def load(name, filename):
    spec=importlib.util.spec_from_file_location(name, BASE/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

release=load("p0_release","css_release_readonly_audit.py")
publisher=load("p0_publisher","publish_css_p0_parallel_status.py")

class P0ParallelTests(unittest.TestCase):
    def test_release_sha_matching_never_approves_browser_or_deploy(self):
        main="a"*40
        result=release.classify(main,{"rootDirectory":"apps/css-sales-workspace"},
            {"deployments":[{"target":"production","state":"READY","created":5,
              "meta":{"githubCommitSha":main}}]})
        self.assertEqual(result["production_sha_parity"],"MATCH")
        self.assertFalse(result["production_release_approved"])
        self.assertFalse(result["deployment_created"])
        self.assertEqual(result["owner_authenticated_browser_e2e"],"NOT_VERIFIED")

    def test_old_sha_and_wrong_workspace_are_blocked(self):
        sha="b"*40
        old="a"*40
        d={"deployments":[{"target":"production","state":"READY","created":5,
              "meta":{"githubCommitSha":old}}]}
        self.assertEqual(release.classify(sha,{"rootDirectory":"apps/css-sales-workspace"},d)
                         ["production_sha_parity"],"BLOCK")
        self.assertEqual(release.classify(old,{"rootDirectory":"research/kalman"},d)
                         ["production_sha_parity"],"BLOCK")

    def test_missing_token_not_presented_as_verification(self):
        obj=release.classify("a"*40,{}, {},has_token=False)
        self.assertEqual(obj["production_sha_parity"],"NOT_CHECKED")
        self.assertFalse(obj["production_release_approved"])

    def test_nine_tracks_are_execution_only(self):
        env={"GITHUB_RUN_ID":"12345","GITHUB_REPOSITORY":"kimtk94/Codex"}
        for _, key, _, _ in publisher.TRACKS:env[key]="success"
        rows=publisher.rows_from_environment(env,"2026-10-31 10:30:00 KST")
        self.assertEqual(9,len(rows))
        self.assertTrue(all(row[1]=="SUCCESS_EXECUTION_ONLY" and row[3]=="NOT_VERIFIED"
                            for row in rows))

    def test_invoice_reviewer_failure_does_not_erase_successful_revenue(self):
        env={"GITHUB_RUN_ID":"12345","GITHUB_REPOSITORY":"kimtk94/Codex"}
        for _,key,_,_ in publisher.TRACKS:env[key]="success"
        env["TRACK_INVOICE_REVIEW"]="failure"
        env["TRACK_OWNER_PAYMENT"]="skipped"
        rows=publisher.rows_from_environment(env,"now")
        by_name={r[0]:r for r in rows}
        self.assertEqual(by_name["Revenue and VAT"][1],"SUCCESS_EXECUTION_ONLY")
        self.assertEqual(by_name["Invoice cross-source gaps"][1],"FAILURE_EXECUTION_ONLY")
        self.assertEqual(by_name["Invoice owner / receipt candidates"][1],"SKIPPED_EXECUTION_ONLY")
        self.assertTrue(all(row[3]=="NOT_VERIFIED" for row in rows))

    def test_all_tracks_have_distinct_keys(self):
        keys=[row[1] for row in publisher.TRACKS]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(9,len(keys))

    def test_evidence_review_lane_has_independent_result(self):
        env={"GITHUB_RUN_ID":"12345","GITHUB_REPOSITORY":"kimtk94/Codex"}
        for _,key,_,_ in publisher.TRACKS:env[key]="success"
        env["TRACK_EVIDENCE"]="failure"
        rows=publisher.rows_from_environment(env,"now")
        by_name={r[0]:r for r in rows}
        self.assertEqual(by_name["Source evidence exceptions"][1],"FAILURE_EXECUTION_ONLY")
        self.assertEqual(by_name["Revenue and VAT"][1],"SUCCESS_EXECUTION_ONLY")
        self.assertEqual(by_name["Source evidence exceptions"][3],"NOT_VERIFIED")

    def test_unrecognized_track_or_repo_is_refused(self):
        env={"GITHUB_RUN_ID":"12345","GITHUB_REPOSITORY":"other/repo"}
        for _, key, _, _ in publisher.TRACKS:env[key]="success"
        with self.assertRaisesRegex(ValueError,"INVALID_GITHUB_RUN_CONTEXT"):
            publisher.rows_from_environment(env,"now")
        env["GITHUB_REPOSITORY"]="kimtk94/Codex"
        env["TRACK_RELEASE"]="unknown"
        with self.assertRaisesRegex(ValueError,"UNKNOWN_PARALLEL_TRACK_STATE"):
            publisher.rows_from_environment(env,"now")

if __name__=="__main__":
    unittest.main()
