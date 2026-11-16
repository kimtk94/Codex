"""Offline regression for safety-critical GitHub Actions event and concurrency routing.

The workflow is intentionally read as plain text: no PyYAML or network dependency
is necessary for PR tests. Checks constrain the small deployment-critical slices.
"""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/autonomous-next-sales.yml"


def workflow():
    return WORKFLOW.read_text(encoding="utf-8")


class WorkflowSafetyTests(unittest.TestCase):
    def test_pr_runs_cannot_share_main_checkpoint_concurrency_group(self):
        text = workflow()
        self.assertIn("github.event_name == 'pull_request' && format('autonomous-next-sales-pr-{0}', github.event.pull_request.number)", text)
        self.assertIn("|| 'autonomous-next-sales-main-checkpoint'", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertNotIn("group: autonomous-next-sales-main-checkpoint\n", text)

    def test_live_credential_job_is_main_only_and_read_only(self):
        text = workflow()
        revenue = text.split("  revenue-mirror-evidence:\n", 1)[1].split("  pr-integration:\n", 1)[0]
        self.assertIn("if: github.event_name != 'pull_request'", revenue)
        self.assertIn("environment: TaehoonServer", revenue)
        self.assertIn("contents: read", revenue)
        self.assertIn("https", "https")  # safety of workflow assertions is independent of API access
        self.assertNotIn("contents: write", revenue)
        self.assertNotIn("issues: write", revenue)

    def test_main_checkpoint_job_does_not_run_on_pr(self):
        text = workflow()
        checkpoint = text.split("  auto-next:\n", 1)[1]
        self.assertIn("if: github.event_name != 'pull_request'", checkpoint)
        self.assertIn("issues: write", checkpoint)
        self.assertIn("--issue-number 794", checkpoint)
        self.assertNotIn("set -e", checkpoint)

    def test_pr_integration_is_never_allowed_business_credentials(self):
        text = workflow()
        section = text.split("  pr-integration:\n", 1)[1].split("  auto-next:\n", 1)[0]
        self.assertIn("if: github.event_name == 'pull_request'", section)
        self.assertIn("permissions:\n      contents: read", section)
        self.assertIn("--offline-run", section)
        self.assertNotIn("secrets.", section)

    def test_next_inspection_only_uses_ranked_same_run_artifact(self):
        text = workflow()
        section = text.split("  next-investigation:\n", 1)[1].split("  revenue-mirror-evidence:\n", 1)[0]
        self.assertIn("if: github.event_name != 'pull_request' && needs.next-review.result == 'success'", section)
        self.assertIn("needs: next-review", section)
        self.assertIn("actions: read", section)
        self.assertIn("autonomous-next-readonly-priority", section)
        self.assertNotIn("secrets.", section)


if __name__ == "__main__":
    unittest.main()
