import tempfile
import unittest
from pathlib import Path
from automation_policy.runner import execute

class RunnerTests(unittest.TestCase):
    def test_normal_execution(self):
        with tempfile.TemporaryDirectory() as d:
            result=execute(Path(d))
            self.assertEqual([v["state"] for v in result["jobs"].values()],["DONE","DONE"])

    def test_retry_then_success(self):
        attempts=[0]
        def flaky(path):
            attempts[0]+=1
            if attempts[0]==1: raise RuntimeError("temporary")
            return {"valid":True}
        with tempfile.TemporaryDirectory() as d:
            result=execute(Path(d),executors={"plan-policy-integrity":flaky,"qc-report":lambda p:{"verified_input":True}})
            self.assertEqual(result["jobs"]["plan-policy-integrity"]["attempts"],2)
            self.assertEqual(result["jobs"]["qc-report"]["state"],"DONE")

    def test_failure_blocks_dependent(self):
        with tempfile.TemporaryDirectory() as d:
            result=execute(Path(d),executors={"plan-policy-integrity":lambda p:{"valid":False},"qc-report":lambda p:{"verified_input":True}})
            self.assertEqual(result["jobs"]["plan-policy-integrity"]["state"],"FAILED_TERMINAL")
            self.assertEqual(result["jobs"]["qc-report"]["state"],"BLOCKED_EXTERNAL")

    def test_missing_executor_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            result=execute(Path(d),executors={})
            self.assertEqual(result["jobs"]["plan-policy-integrity"]["reason"],"EXECUTOR_NOT_CONNECTED")
