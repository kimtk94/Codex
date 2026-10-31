"""Offline safety tests for central workflow status publishing."""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).parent))
from publish_central_workflow_health import evaluate_runs,make_rows,bi_job_result,WORKFLOWS,UTC

NOW=dt.datetime(2026,10,30,0,0,tzinfo=UTC)

def run(id=1,conclusion="success",updated="2026-10-29T23:00:00Z",
        status="completed",branch="main"):
    return {"id":id,"head_branch":branch,"created_at":updated,
            "updated_at":updated,"status":status,"conclusion":conclusion,
            "event":"schedule"}

class PublisherTests(unittest.TestCase):
    def test_recent_success_means_execution_not_business_acceptance(self):
        s,at,age,event,item=evaluate_runs([run()],NOW,6)
        self.assertEqual(s,"PASS_EXECUTION_ONLY")
        self.assertEqual(age,1.0)
        self.assertEqual(event,"schedule")
        self.assertIn("2026-",at)
    def test_real_failure_not_hidden_by_older_success(self):
        a=run(22,conclusion="failure")
        b=run(21,updated="2026-10-29T22:00:00Z")
        s,*_=evaluate_runs([b,a],NOW,24)
        self.assertEqual(s,"FAILED")
    def test_stale_success_is_not_green(self):
        s,*_=evaluate_runs([run(updated="2026-10-28T10:00:00Z")],NOW,12)
        self.assertEqual(s,"STALE")
    def test_main_only_no_branch_preview_spoof(self):
        s,*_=evaluate_runs([run(branch="pull/394")],NOW,6)
        self.assertEqual(s,"NOT_RUN")
    def test_running_workflow_not_passed(self):
        s,*_=evaluate_runs([run(status="in_progress",conclusion=None)],NOW,6)
        self.assertEqual(s,"IN_PROGRESS")
    def test_unknown_conclusion_never_passes(self):
        s,*_=evaluate_runs([run(conclusion="unknown_value")],NOW,6)
        self.assertEqual(s,"UNVERIFIED")
    def test_null_or_malformed_run_id_fails_before_sheet_write(self):
        with self.assertRaisesRegex(ValueError,"INVALID_ACTIONS_RUN_ID"):
            make_rows(lambda filename:[run(id="bad")],NOW)
    def test_output_schema_is_fixed_to_one_row_per_workflow(self):
        rows=make_rows(lambda filename:[run(id=98765)],NOW)
        self.assertEqual(len(rows),len(WORKFLOWS)+1)
        self.assertEqual(len(rows[0]),10)
        self.assertTrue(all(len(row)==10 for row in rows))
        self.assertTrue(all(r[5]=="https://github.com/kimtk94/Codex/actions/runs/98765"
                            for r in rows[1:]))
        self.assertIn("Feishu Schema Audit",[r[0] for r in rows])
        self.assertIn("Web Console CI",[r[0] for r in rows])
        self.assertIn("Verified Net Revenue VAT",[r[0] for r in rows])
        self.assertIn("CSS API Source Contract",[r[0] for r in rows])
        api=next(r for r in rows if r[0]=="CSS API Source Contract")
        self.assertIn("NOT Vercel OAuth/Preview E2E",api[8])
        self.assertEqual(api[9],"css-source-backed-api-contract.yml")
    def test_all_critical_workflows_have_independent_recent_status(self):
        expected={"css-p0-parallel-verification.yml",
                  "css-vercel-build-scope-guard.yml",
                  "css-operational-acceptance.yml",
                  "sales-payment-reconciliation.yml"}
        refs=[entry[2] for entry in WORKFLOWS]
        self.assertEqual(len(refs),len(set(refs)))
        self.assertTrue(expected.issubset(set(refs)))
        rows=make_rows(lambda filename:[run(id=98765)],NOW)
        self.assertEqual(len(rows),18)
        self.assertTrue(all(row[2]=="PASS_EXECUTION_ONLY" for row in rows[1:]))
        policy=next(row for row in rows if row[0]=="CSS Release Policy")
        self.assertIn("not certified",policy[8].lower())

    def test_bi_workflow_failure_is_not_mislabeled_as_sync_failure(self):
        jobs=[{"name":"sync","status":"completed","conclusion":"success"},
              {"name":"test","status":"completed","conclusion":"failure"}]
        rows=make_rows(lambda filename:[run(id=123,conclusion="failure")],NOW,
                       job_fetch=lambda run_id: jobs)
        bi=next(row for row in rows[1:] if row[0]=="BI Mail Review Sync")
        self.assertEqual(bi[2],"FAILED")
        self.assertIn("BI_JOB_DETAILS_SYNC_SUCCESS_TEST_FAILURE",bi[8])
        self.assertNotIn("mail sent",bi[8].lower())

    def test_real_sync_failure_remains_explicit_and_fail_closed(self):
        jobs=[{"name":"sync","status":"completed","conclusion":"failure"},
              {"name":"test","status":"completed","conclusion":"success"}]
        rows=make_rows(lambda filename:[run(id=123,conclusion="failure")],NOW,
                       job_fetch=lambda run_id: jobs)
        bi=next(row for row in rows[1:] if row[0]=="BI Mail Review Sync")
        self.assertEqual(bi[2],"FAILED")
        self.assertIn("BI_JOB_DETAILS_SYNC_FAILURE_TEST_SUCCESS",bi[8])

    def test_bi_job_detail_unavailable_never_upgrades_failing_run(self):
        def missing(run_id):raise RuntimeError("API_LIMIT")
        rows=make_rows(lambda filename:[run(id=123,conclusion="failure")],NOW,
                       job_fetch=missing)
        bi=next(row for row in rows[1:] if row[0]=="BI Mail Review Sync")
        self.assertEqual(bi[2],"FAILED")
        self.assertIn("BI_JOB_DETAILS_UNAVAILABLE",bi[8])

    def test_bi_job_duplicate_name_is_not_arbitrarily_resolved(self):
        self.assertEqual(bi_job_result([{"name":"sync","conclusion":"success"},
                                        {"name":"sync","conclusion":"failure"}]),
                         "AMBIGUOUS_JOB_DETAILS_REVIEW")

    def test_cancelled_newer_run_stays_cancelled_even_with_recent_success(self):
        cancelled=run(901,conclusion="cancelled",updated="2026-10-29T23:30:00Z")
        older_success=run(900,conclusion="success",updated="2026-10-29T23:15:00Z")
        rows=make_rows(lambda filename:[cancelled,older_success],NOW)
        report=next(row for row in rows[1:] if row[0]=="SFDC 3-Report Ingest")
        self.assertEqual(report[2],"CANCELLED")
        self.assertIn("RECENT_SUCCESS_RUN_ID=900",report[8])
        self.assertIn("CANCELLED_OR_SKIPPED_NOT_CERTIFIED",report[8])
        self.assertIn("/actions/runs/901",report[5])

    def test_cancelled_without_recent_success_is_not_hid(self):
        cancelled=run(901,conclusion="cancelled",updated="2026-10-29T23:30:00Z")
        old_success=run(880,conclusion="success",updated="2026-10-20T10:00:00Z")
        rows=make_rows(lambda filename:[cancelled,old_success],NOW)
        report=next(row for row in rows[1:] if row[0]=="SFDC 3-Report Ingest")
        self.assertEqual(report[2],"CANCELLED")
        self.assertIn("NO_RECENT_SUCCESS_EVIDENCE",report[8])

    def test_failure_never_gets_success_exception(self):
        failed=run(902,conclusion="failure")
        earlier=run(901,conclusion="success",updated="2026-10-29T22:30:00Z")
        rows=make_rows(lambda filename:[failed,earlier],NOW)
        report=next(row for row in rows[1:] if row[0]=="SFDC 3-Report Ingest")
        self.assertEqual(report[2],"FAILED")
        self.assertNotIn("RECENT_SUCCESS_RUN_ID",report[8])

    def test_no_runs_flags_missing_not_optimistic(self):
        rows=make_rows(lambda filename:[],NOW)
        self.assertEqual(len(rows),len(WORKFLOWS)+1)
        self.assertTrue(all(r[2]=="NOT_RUN" for r in rows[1:]))

if __name__=="__main__":
    unittest.main()
