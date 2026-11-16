"""Unit tests for autonomous-next. All mocked; no GitHub or SFDC connections."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner


def plan():
    return json.loads(runner.PLAN_PATH.read_text(encoding="utf-8"))


class FakeCheckpoint:
    def __init__(self):
        self.snapshots = []
        self.paused_flag = False
        self.pause_after = None

    def paused(self):
        return self.paused_flag or (self.pause_after is not None and len(self.snapshots) >= self.pause_after)

    def save(self, state):
        self.snapshots.append(copy.deepcopy(state))


class AutonomousNextTests(unittest.TestCase):
    def setUp(self):
        self.p = plan()
        runner.validate_plan(self.p)
        self.s = runner.fresh_state(self.p, "abc", "https://github.com/kimtk94/Codex/actions/runs/123")

    def test_all_six_tasks_progress_without_further_prompt(self):
        store = FakeCheckpoint()
        with patch.object(runner, "execute_suite", return_value=(True, "synthetic pass")) as exe:
            result = runner.run(self.p, self.s, max_steps=6,
                                checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("TEST_CHAIN_PASS", result["overall"])
        self.assertEqual(6, exe.call_count)
        self.assertEqual(0, sum(x["status"] != "PASS" for x in result["tasks"].values()))
        self.assertGreaterEqual(len(store.snapshots), 13)
        self.assertFalse(result["policy"]["sfdc_save"])
        self.assertFalse(result["policy"]["live_source_verified"])

    def test_bounded_run_resume_does_not_repeat_passed_tasks(self):
        with patch.object(runner, "execute_suite", return_value=(True, "")) as exe:
            runner.run(self.p, self.s, max_steps=2,
                       checkpoint=None, root=runner.ROOT, dry_run=False)
            self.assertEqual("PARTIAL", self.s["overall"])
            self.assertEqual(2, exe.call_count)
            runner.run(self.p, self.s, max_steps=4,
                       checkpoint=None, root=runner.ROOT, dry_run=False)
        self.assertEqual("TEST_CHAIN_PASS", self.s["overall"])
        self.assertEqual(6, exe.call_count)

    def test_fail_stops_queue_then_retry_can_resume(self):
        with patch.object(runner, "execute_suite", side_effect=[(True, ""), (False, "synthetic error"),
                                                                 (True, ""), (True, ""), (True, ""), (True, ""), (True, "")]) as exe:
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=None, root=runner.ROOT, dry_run=False)
            self.assertEqual("FAILED_RETRYABLE", self.s["overall"])
            self.assertEqual(2, exe.call_count)
            self.assertEqual("sfdc-oppo-quote", runner.next_task(self.p, self.s)["id"])
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=None, root=runner.ROOT, dry_run=False)
        self.assertEqual("TEST_CHAIN_PASS", self.s["overall"])
        self.assertEqual(2, self.s["tasks"]["sfdc-oppo-quote"]["attempts"])

    def test_three_failures_become_blocked_without_running_downstream(self):
        with patch.object(runner, "execute_suite", return_value=(False, "bad")) as exe:
            for _ in range(3):
                runner.run(self.p, self.s, max_steps=6,
                           checkpoint=None, root=runner.ROOT, dry_run=False)
            self.assertEqual("BLOCKED", self.s["overall"])
            self.assertIsNone(runner.next_task(self.p, self.s))
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=None, root=runner.ROOT, dry_run=False)
        self.assertEqual(3, exe.call_count)
        self.assertEqual(1, len(self.s["tasks"]))

    def test_dry_run_does_not_execute_or_claim_pass(self):
        with patch.object(runner, "execute_suite", side_effect=AssertionError("should not execute")):
            runner.run(self.p, self.s, max_steps=6, checkpoint=None,
                       root=runner.ROOT, dry_run=True)
        self.assertEqual("DRY_RUN_NO_EXECUTION", self.s["overall"])
        self.assertEqual({}, self.s["tasks"])

    def test_unknown_suite_and_out_of_order_dependencies_denied(self):
        p = plan()
        p["tasks"][0]["suite"] = "arbitrary_shell"
        with self.assertRaises(ValueError):
            runner.validate_plan(p)
        p = plan()
        p["tasks"][0]["depends_on"] = ["sfdc-krw-price"]
        with self.assertRaises(ValueError):
            runner.validate_plan(p)

    def test_source_sha_or_expiry_resets_checkpoint(self):
        self.assertTrue(runner.reusable(self.s, self.p, "abc"))
        self.assertFalse(runner.reusable(self.s, self.p, "other"))
        date = dt.datetime.fromisoformat(self.s["started_at"]) + dt.timedelta(hours=25)
        self.assertFalse(runner.reusable(self.s, self.p, "abc", current=date))

    def test_issue_body_preserves_user_notes(self):
        cp = object.__new__(runner.IssueCheckpoint)
        cp.body = "Old notes\n" + runner.START + "\n{}\n" + runner.END
        records = []
        live_body = "Manual notes updated later\n" + runner.RUN_CHECKBOX + "\n" + runner.START + "\n{}\n" + runner.END + "\nKeep this"
        def request(method, payload=None):
            if method == "GET":
                return {"body": live_body}
            records.append((method, payload))
            return {}
        cp.request = request
        cp.save(self.s)
        body = records[0][1]["body"]
        self.assertIn("Manual notes updated later", body)
        self.assertIn("Keep this", body)
        self.assertEqual(self.s["head_sha"], json.loads(
            body.split(runner.START)[1].split(runner.END)[0])["head_sha"])

    def test_operator_pause_before_first_stage(self):
        store = FakeCheckpoint()
        store.paused_flag = True
        with patch.object(runner, "execute_suite", side_effect=AssertionError("paused")):
            result = runner.run(self.p, self.s, max_steps=6,
                                checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("PAUSED_BY_OPERATOR", result["overall"])
        self.assertEqual(0, len(result["tasks"]))

    def test_pause_between_stages_and_resume_safely(self):
        store = FakeCheckpoint()
        store.pause_after = 2
        with patch.object(runner, "execute_suite", return_value=(True, "")) as exe:
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=store, root=runner.ROOT, dry_run=False)
            self.assertEqual("PAUSED_BY_OPERATOR", self.s["overall"])
            self.assertEqual(1, exe.call_count)
            store.pause_after = None
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("TEST_CHAIN_PASS", self.s["overall"])
        self.assertEqual(6, exe.call_count)

    def test_pause_during_checkpoint_save_prevents_suite_launch_and_refunds_attempt(self):
        class PauseDuringFirstSave(FakeCheckpoint):
            def save(self, state):
                super().save(state)
                if len(self.snapshots) == 1:
                    self.paused_flag = True

        store = PauseDuringFirstSave()
        with patch.object(runner, "execute_suite",
                          side_effect=AssertionError("must not launch after pause")):
            result = runner.run(self.p, self.s, max_steps=6,
                                checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("PAUSED_BY_OPERATOR", result["overall"])
        self.assertEqual({}, result["tasks"])
        self.assertEqual({}, store.snapshots[-1]["tasks"])
        store.paused_flag = False
        with patch.object(runner, "execute_suite", return_value=(True, "")) as execute:
            runner.run(self.p, self.s, max_steps=6,
                       checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("TEST_CHAIN_PASS", self.s["overall"])
        self.assertEqual(6, execute.call_count)
        self.assertEqual(1, self.s["tasks"]["policy-guard"]["attempts"])

    def test_pause_during_retry_preserves_existing_failed_attempt_count(self):
        class PauseDuringFirstSave(FakeCheckpoint):
            def save(self, state):
                super().save(state)
                if len(self.snapshots) == 1:
                    self.paused_flag = True

        self.s["tasks"]["policy-guard"] = {
            "status": "FAILED", "attempts": 2,
            "suite": "policy", "failure_code": "OFFLINE_SUITE_NONZERO_EXIT",
        }
        store = PauseDuringFirstSave()
        with patch.object(runner, "execute_suite",
                          side_effect=AssertionError("pause prevents retry")):
            runner.run(self.p, self.s, max_steps=6, checkpoint=store,
                       root=runner.ROOT, dry_run=False)
        self.assertEqual(2, self.s["tasks"]["policy-guard"]["attempts"])
        self.assertEqual("FAILED", self.s["tasks"]["policy-guard"]["status"])
        self.assertEqual("PAUSED_BY_OPERATOR", self.s["overall"])

    def test_operator_pause_checkbox_fail_closed_if_missing(self):
        cp = object.__new__(runner.IssueCheckpoint)
        body = "Notes\n" + runner.START + "\n{}\n" + runner.END
        cp.request = lambda method, payload=None: {"body": body}
        with self.assertRaises(ValueError):
            cp.paused()
        body = runner.PAUSE_CHECKBOX + "\n" + runner.START + "\n{}\n" + runner.END
        self.assertTrue(cp.paused())
        body = runner.RUN_CHECKBOX + "\n" + runner.START + "\n{}\n" + runner.END
        self.assertFalse(cp.paused())

    def test_receipt_is_explicitly_synthetic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = runner.report(self.p, self.s, Path(tmp))
            self.assertIn("NOT VERIFIED", summary)
            self.assertIn("Remaining stages: **6**", summary)
            self.assertTrue((Path(tmp) / "state.json").exists())

    def test_failed_suite_never_leaks_stdout_stderr_or_credentials(self):
        private = "CONFIDENTIAL_CUSTOMER_MAIL_AND_INVOICE_010203"
        class Failed:
            returncode = 2
            stdout = private
            stderr = private + " MISSING_PRIVATE_SECRET"
        with patch.dict(runner.os.environ, {
            "GITHUB_TOKEN": private, "QQ_PASSWORD": private,
            "FEISHU_APP_ID": private, "CKD_DRIVE_SA_JSON": private,
            "GCP_SERVICE_ACCOUNT_JSON": private, "API_TOKEN": private,
            "OPENAI_API_KEY": private,
        }):
            with patch.object(runner.subprocess, "run", return_value=Failed()) as mock_run:
                ok, diagnostic = runner.execute_suite("policy")
        self.assertFalse(ok)
        self.assertEqual("OFFLINE_SUITE_NONZERO_EXIT", diagnostic)
        _, kwargs = mock_run.call_args
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("QQ_PASSWORD", kwargs["env"])
        self.assertNotIn("CKD_DRIVE_SA_JSON", kwargs["env"])
        self.assertNotIn("GCP_SERVICE_ACCOUNT_JSON", kwargs["env"])
        self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
        self.assertNotIn("API_TOKEN", kwargs["env"])
        self.assertEqual("", kwargs["env"]["FEISHU_APP_ID"])
        self.assertNotIn(private, str(kwargs["env"]))
        self.assertNotIn(private, diagnostic)

    def test_failed_checkpoint_writes_only_sanitized_failure_code(self):
        private = "PRIVATE_INVOICE_CONTACT_010203"
        store = FakeCheckpoint()
        with patch.object(runner, "execute_suite", return_value=(False, private)):
            result = runner.run(self.p, self.s, max_steps=6,
                                checkpoint=store, root=runner.ROOT, dry_run=False)
        self.assertEqual("FAILED_RETRYABLE", result["overall"])
        entry = result["tasks"]["policy-guard"]
        self.assertEqual("OFFLINE_SUITE_FAILED_UNCLASSIFIED", entry["failure_code"])
        self.assertNotIn("failure_excerpt", entry)
        self.assertNotIn(private, json.dumps(result))
        self.assertTrue(all(private not in json.dumps(snapshot) for snapshot in store.snapshots))
        with tempfile.TemporaryDirectory() as temp:
            runner.report(self.p, result, Path(temp))
            self.assertNotIn(private, (Path(temp) / "state.json").read_text())

    def test_timeout_is_code_only(self):
        with patch.object(runner.subprocess, "run",
                          side_effect=runner.subprocess.TimeoutExpired(cmd=["python3"], timeout=3)):
            ok, code = runner.execute_suite("policy", timeout=3)
        self.assertFalse(ok)
        self.assertEqual("OFFLINE_SUITE_TIMED_OUT", code)

    def test_execute_suite_has_no_shell_or_live_credentials(self):
        class Result:
            returncode = 0
            stdout = "OK"
            stderr = ""
        with patch.dict(runner.os.environ, {"GITHUB_TOKEN": "hidden", "FEISHU_APP_ID": "hidden"}):
            with patch.object(runner.subprocess, "run", return_value=Result()) as mocked:
                ok, _ = runner.execute_suite("sfdc_patterns")
        self.assertTrue(ok)
        args, kwargs = mocked.call_args
        self.assertEqual("python3", args[0][0])
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
        self.assertEqual("", kwargs["env"]["FEISHU_APP_ID"])


if __name__ == "__main__":
    unittest.main()
