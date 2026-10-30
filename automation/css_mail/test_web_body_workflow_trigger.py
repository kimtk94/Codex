"""Validate that web body backfill waits for successful QQ source completion."""
from pathlib import Path
import unittest
WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/css-web-body-sync.yml")
SOURCE = (Path(__file__).resolve().parents[2] / ".github/workflows/css-mail-readonly.yml")
class TriggerTests(unittest.TestCase):
    def test_verified_upstream_and_success_gate(self):
        body=WORKFLOW.read_text(encoding="utf-8")
        source=SOURCE.read_text(encoding="utf-8")
        self.assertIn("workflows: [\"CSS QQ Mail Read-only Probe\"]",body)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",body)
        self.assertIn("github.event.workflow_run.head_branch == 'main'",body)
        self.assertIn("name: CSS QQ Mail Read-only Probe",source)
    def test_no_competing_30_minute_schedule_and_shared_lock(self):
        body=WORKFLOW.read_text(encoding="utf-8")
        source=SOURCE.read_text(encoding="utf-8")
        self.assertIn("css-qq-mail-readonly",body)
        self.assertIn("group: css-qq-mail-readonly",source)
        self.assertNotIn("17,47 * * * *",body)
        self.assertIn("47 0,6,12,18 * * *",body)
        self.assertIn("cancel-in-progress: false",body)
    def test_batch_is_bounded_and_no_sends(self):
        body=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("CSS_WEB_BODY_BATCH: '160'",body)
        self.assertIn("web_body_serial_runner.py",body)
        self.assertIn("CSS_WEB_BODY_SERIAL_CYCLES: '3'",body)
        self.assertNotIn("send_customer_mail.py",body)
if __name__=="__main__":unittest.main()
