"""Fail-closed workflow provenance and concurrency grouping regression checks.

GitHub Actions allows one running + one pending per concurrency group.
A PR-only research run cannot be allowed to evict a scheduled first seal.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/kalman-daily20.yml"
EXPECTED_CRONS = ("40 2 * * 2-6", "40 4 * * 2-6")
PIPELINE_CONTRACT = (
    "research/kalman_daily20/next_session_two_pass_contract.py"
)


class ScheduledHandoffConcurrencyStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = WORKFLOW.read_text(encoding="utf-8")

    def test_pr_research_has_per_pr_group_not_protected_main_group(self):
        value = self.raw
        self.assertIn("github.event_name == 'pull_request'", value)
        self.assertIn("format('pr-{0}', github.event.pull_request.number)", value)
        self.assertIn("|| 'protected-main'", value)
        self.assertNotIn("group: kalman-daily20-research\n", value)

    def test_protected_main_writers_remain_serialized(self):
        value = self.raw
        self.assertIn("group: kalman-daily20-research-", value)
        self.assertIn("cancel-in-progress: false", value)
        self.assertIn("|| 'protected-main'", value)
        self.assertIn("persist-google-drive:", value)
        self.assertIn("if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' || github.event_name == 'push'", value)

    def test_both_exact_original_schedule_slots_are_retained(self):
        raw = self.raw
        for schedule in EXPECTED_CRONS:
            self.assertIn("cron: '" + schedule + "'", raw)
        self.assertEqual(raw.count("cron: '40 "), 2)

    def test_event_name_and_schedule_role_verified_at_both_boundaries(self):
        raw = self.raw
        self.assertEqual(raw.count("python " + PIPELINE_CONTRACT), 2)
        self.assertEqual(raw.count('--event-name "${{ github.event_name }}"'), 2)
        self.assertEqual(raw.count('--schedule-slot "${{ github.event.schedule }}"'), 2)
        self.assertIn('assert r["github_event_origin"]=="${{ github.event_name }}"', raw)
        self.assertIn("r[\"expected_new_bull\"]==r[\"expected_new_bear\"]==0", raw)

    def test_no_auto_live_or_broker_writes_added(self):
        raw = self.raw
        self.assertIn("Kalman Daily 20 Research (No Server / No Live)", raw)
        self.assertIn("source_finality_verified_assets", raw)
        self.assertIn("assert r[\"research_hold\"]", raw)


if __name__ == "__main__":
    unittest.main()
