"""No duplicate, unverified, or uncontrolled automated writer dispatch."""
import datetime as dt
import io
import json
import unittest
from unittest.mock import patch

from css_writer_schedule_watchdog import (
    inspect, reconcile, request_json, applied_dispatch_job_ids, FEISHU, QQ, REPO,
)

NOW=dt.datetime(2026,11,23,12,0,tzinfo=dt.timezone.utc)


def run(hours, status="completed", result="success", event="schedule",
        branch="main"):
    created=NOW-dt.timedelta(hours=hours)
    return {"event":event,"head_branch":branch,
            "created_at":created.isoformat().replace("+00:00","Z"),
            "status":status,"conclusion":result}


class RecurringWatchdogTests(unittest.TestCase):
    def test_history_queries_exclude_pr_noise_even_under_high_test_volume(self):
        scheduled=dict(run(10),id=600)
        manually_applied=dict(run(2,event="workflow_dispatch"),id=601)
        captured=[]
        def fake_urlopen(request,timeout):
            url=request.full_url
            captured.append(url)
            if "event=schedule" in url:
                body={"workflow_runs":[scheduled]}
            elif "event=workflow_dispatch" in url:
                body={"workflow_runs":[manually_applied]}
            else:
                raise AssertionError("UNSCOPED_HISTORY_REQUEST")
            return io.BytesIO(json.dumps(body).encode())
        with patch("css_writer_schedule_watchdog.urllib.request.urlopen",
                   side_effect=fake_urlopen):
            result=request_json(REPO,FEISHU,"PRIVATE_TOKEN")
        self.assertEqual({x["id"] for x in result},{600,601})
        self.assertEqual(len(captured),2)
        self.assertTrue(all("branch=main" in url for url in captured))
        self.assertTrue(all("per_page=40" in url for url in captured))

    def test_history_api_wrong_event_fails_closed(self):
        scheduled=dict(run(10,event="pull_request"),id=620)
        with patch("css_writer_schedule_watchdog.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(
                       {"workflow_runs":[scheduled]}).encode())):
            with self.assertRaisesRegex(RuntimeError,"WORKFLOW_RUN_HISTORY_SCOPE_INVALID"):
                request_json(REPO,FEISHU,"PRIVATE_TOKEN")

    def test_health_publisher_fallback_cannot_create_workflow_run_cycle(self):
        import pathlib
        root=pathlib.Path(__file__).resolve().parents[2] / ".github/workflows"
        watchdog=(root/"css-recurring-sources-watchdog.yml").read_text(encoding="utf-8")
        publisher=(root/"css-central-workflow-health.yml").read_text(encoding="utf-8")
        self.assertIn("- 'CSS Central Workflow Health Publisher'",watchdog)
        self.assertIn("github.event.workflow_run.event == 'schedule'",watchdog)
        self.assertIn("- 'Feishu Sources Payment Online Monthly Unified'",publisher)
        # Do not subscribe central publisher to watchdog completion:
        # that would cause self-sustaining workflow_run/test-only chains.
        self.assertNotIn("'CSS Recurring Source Writer Watchdog (Safe Recovery)'",publisher)

    def test_recent_success_no_new_write(self):
        state=inspect([run(2),run(5)],NOW,6)
        self.assertEqual(state["state"],"RECENT_SCHEDULE_SUCCESS")
        self.assertFalse(state["eligible"])
        called=[]
        z=reconcile([run(2)],[run(2)],NOW,True,lambda:called.append("dispatch"))
        self.assertEqual(called,[])
        self.assertEqual(z["dispatch_state"],"NOT_REQUESTED")

    def test_verified_recovered_writer_resets_staleness_without_repeating(self):
        old = dict(run(11),id=100)
        recovered = dict(run(1,event="workflow_dispatch"),id=200)
        r = inspect([old,recovered], NOW, 6, verified_applied_ids={200})
        self.assertEqual(r["state"],"RECENT_VERIFIED_RECOVERY_SUCCESS")
        self.assertTrue(r["verified_recovered_success"])
        self.assertFalse(r["eligible"])
        called = []
        out = reconcile([old,recovered],[run(2)],NOW,True,
                        lambda:called.append(FEISHU),
                        verified_applied_ids={200})
        self.assertEqual(called,[])
        self.assertEqual(out["dispatch_state"],"NOT_REQUESTED")

    def test_unverified_green_manual_tests_do_not_certify_recovery(self):
        old = dict(run(11),id=100)
        manual = dict(run(1,event="workflow_dispatch"),id=201)
        self.assertEqual(inspect([old,manual],NOW,6)["state"],"COOLDOWN_WAIT")
        self.assertEqual(inspect([old,manual],NOW,6,
                                 verified_applied_ids={999})["state"],"COOLDOWN_WAIT")

    def test_applied_dispatch_requires_all_jobs_and_untruncated_history(self):
        manual = dict(run(1,event="workflow_dispatch"),id=345)
        records=[
            {"name":name,"status":"completed","conclusion":"success"}
            for name in ("tests","ingest","payment","lifecycle","monthly")
        ]

        def fake_urlopen_success(request,timeout):
            self.assertIn("/actions/runs/345/jobs",request.full_url)
            return io.BytesIO(json.dumps({"total_count":5,"jobs":records}).encode())

        with patch("css_writer_schedule_watchdog.urllib.request.urlopen",
                   side_effect=fake_urlopen_success):
            self.assertEqual(applied_dispatch_job_ids(REPO,"PRIVATE_TOKEN",
                                                      [manual],NOW),{345})
        incomplete={"total_count":5,"jobs":records[:4]}
        with patch("css_writer_schedule_watchdog.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(incomplete).encode())):
            with self.assertRaisesRegex(RuntimeError,"RECOVERY_JOBS_TRUNCATED"):
                applied_dispatch_job_ids(REPO,"PRIVATE_TOKEN",[manual],NOW)
        skipped={"total_count":5,"jobs":[dict(x,conclusion="skipped")
                             if x["name"]=="ingest" else x for x in records]}
        with patch("css_writer_schedule_watchdog.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(skipped).encode())):
            self.assertEqual(applied_dispatch_job_ids(REPO,"PRIVATE_TOKEN",
                                                       [manual],NOW),set())

    def test_applied_dispatch_unverifiable_id_or_timestamp_fails_closed(self):
        manual=dict(run(1,event="workflow_dispatch"),id="345")
        with self.assertRaisesRegex(RuntimeError,"RECOVERY_RUN_ID_UNVERIFIED"):
            applied_dispatch_job_ids(REPO,"PRIVATE_TOKEN",[manual],NOW)
        manual["id"]=345
        manual["created_at"]="not-a-timestamp"
        with self.assertRaisesRegex(RuntimeError,"RECOVERY_RUN_TIMESTAMP_UNVERIFIED"):
            applied_dispatch_job_ids(REPO,"PRIVATE_TOKEN",[manual],NOW)

    def test_stale_triggers_one_existing_writer_only(self):
        called=[]
        result=reconcile([run(9)],[run(2)],NOW,True,
                         lambda:called.append(FEISHU))
        self.assertEqual(called,[FEISHU])
        self.assertEqual(result["dispatch_state"],"EXISTING_FEISHU_WRITER_REQUESTED")
        self.assertFalse(result["qq_historical_auto_replay"])
        self.assertFalse(result["financial_original_writes"])

    def test_recent_attempt_uses_cooldown(self):
        state=inspect([run(1,"completed","failure"),run(10)],NOW,6)
        self.assertEqual(state["state"],"RECENT_FAILURE_HOLD")
        self.assertFalse(state["eligible"])
        state=inspect([run(2,"completed","success","workflow_dispatch"),run(10)],
                      NOW,6)
        self.assertEqual(state["state"],"COOLDOWN_WAIT")
        self.assertFalse(state["eligible"])

    def test_prior_recent_pass_does_not_mask_latest_failure(self):
        result=inspect([run(4,"completed","failure"),run(5)],NOW,6)
        self.assertEqual(result["state"],"LATEST_FAILURE_HOLD")
        self.assertFalse(result["eligible"])
        result=inspect([run(1,"completed","failure"),run(2)],NOW,6)
        self.assertEqual(result["state"],"RECENT_FAILURE_HOLD")
        self.assertFalse(result["eligible"])

    def test_running_and_stalled_runs_never_race(self):
        state=inspect([run(1,"in_progress",None),run(10)],NOW,6)
        self.assertEqual(state["state"],"RUNNING")
        self.assertFalse(state["eligible"])
        state=inspect([run(7,"in_progress",None),run(10)],NOW,6)
        self.assertEqual(state["state"],"STALLED_RUN_HOLD")
        self.assertFalse(state["eligible"])

    def test_missing_production_history_or_baseline_no_dispatch(self):
        self.assertEqual(inspect([],NOW,6)["state"],"NO_PRODUCTION_HISTORY_HOLD")
        self.assertEqual(inspect([run(12,event="pull_request")],NOW,6)["state"],
                         "NO_PRODUCTION_HISTORY_HOLD")
        self.assertEqual(inspect([run(12,result="failure")],NOW,6)["state"],
                         "NO_SUCCESS_BASELINE_HOLD")
        self.assertEqual(inspect([run(12,event="workflow_dispatch")],NOW,6)["state"],
                         "NO_SUCCESS_BASELINE_HOLD")

    def test_no_dispatch_if_auto_opt_out(self):
        called=[]
        z=reconcile([run(10)],[run(10)],NOW,False,
                    lambda:called.append("dispatch"))
        self.assertEqual(called,[])
        self.assertEqual(z["dispatch_state"],"ELIGIBLE_REPORT_ONLY")

    def test_ignore_pull_request_and_other_branch_success(self):
        s=inspect([run(1,event="pull_request"),run(2,branch="feature"),
                   run(11)],NOW,6)
        self.assertEqual(s["state"],"STALE_WRITER_ELIGIBLE")

    def test_unverified_or_future_run_not_zero_or_success(self):
        self.assertEqual(inspect(None,NOW,6)["state"],"RUN_HISTORY_UNVERIFIED")
        self.assertEqual(inspect([{"event":"schedule","head_branch":"main",
                          "created_at":"UNKNOWN"}],NOW,6)["state"],
                         "RUN_HISTORY_UNVERIFIED")
        self.assertEqual(inspect([run(-3)],NOW,6)["state"],"RUN_HISTORY_UNVERIFIED")

    def test_qq_monitor_never_auto_dispatches_qq(self):
        invoked=[]
        out=reconcile([run(2)],[run(20)],NOW,True,
                      lambda:invoked.append(QQ))
        self.assertEqual(out["qq_2026"]["state"],"STALE_WRITER_ELIGIBLE")
        self.assertEqual(invoked,[])
        self.assertFalse(out["qq_historical_auto_replay"])

    def test_failed_dispatch_keeps_failure_explicit(self):
        with self.assertRaisesRegex(RuntimeError,"SIMULATED_API_FAILURE"):
            reconcile([run(10)],[run(2)],NOW,True,
                      lambda: (_ for _ in ()).throw(
                          RuntimeError("SIMULATED_API_FAILURE")))


if __name__=="__main__":
    unittest.main()
