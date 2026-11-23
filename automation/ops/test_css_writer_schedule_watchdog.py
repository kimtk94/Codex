"""No duplicate, unverified, or uncontrolled automated writer dispatch."""
import datetime as dt
import unittest

from css_writer_schedule_watchdog import inspect, reconcile, FEISHU, QQ

NOW=dt.datetime(2026,11,23,12,0,tzinfo=dt.timezone.utc)


def run(hours, status="completed", result="success", event="schedule",
        branch="main"):
    created=NOW-dt.timedelta(hours=hours)
    return {"event":event,"head_branch":branch,
            "created_at":created.isoformat().replace("+00:00","Z"),
            "status":status,"conclusion":result}


class RecurringWatchdogTests(unittest.TestCase):
    def test_recent_success_no_new_write(self):
        state=inspect([run(2),run(5)],NOW,6)
        self.assertEqual(state["state"],"RECENT_SCHEDULE_SUCCESS")
        self.assertFalse(state["eligible"])
        called=[]
        z=reconcile([run(2)],[run(2)],NOW,True,lambda:called.append("dispatch"))
        self.assertEqual(called,[])
        self.assertEqual(z["dispatch_state"],"NOT_REQUESTED")

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
