#!/usr/bin/env python3
"""Ensure canonical Revenue refresh triggers native KPI card re-publication."""
import pathlib
import unittest

WF=pathlib.Path(__file__).resolve().parents[2]/".github/workflows/feishu-native-kpi-dashboard.yml"


class RevenueCardTriggerTests(unittest.TestCase):
    def test_successful_monthly_actual_sync_triggers_card_apply(self):
        source=WF.read_text(encoding="utf-8")
        self.assertIn("workflow_run:",source)
        self.assertIn("workflows: ['Feishu Canonical Monthly Revenue Actual']",source)
        self.assertIn("types: [completed]",source)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",source)
        self.assertIn("(github.event_name == 'schedule' || github.event_name == 'workflow_run') && 'apply'",source)
        self.assertIn("cancel-in-progress: false",source)


if __name__=="__main__":
    unittest.main()
