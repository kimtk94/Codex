"""Offline safety tests for central workflow status publishing."""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).parent))
from publish_central_workflow_health import evaluate_runs,make_rows,WORKFLOWS,UTC

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
    def test_no_runs_flags_missing_not_optimistic(self):
        rows=make_rows(lambda filename:[],NOW)
        self.assertEqual(len(rows),len(WORKFLOWS)+1)
        self.assertTrue(all(r[2]=="NOT_RUN" for r in rows[1:]))

if __name__=="__main__":
    unittest.main()
