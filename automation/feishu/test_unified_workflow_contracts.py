#!/usr/bin/env python3
"""Pipeline ownership and source publication regression tests."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
W=ROOT/".github/workflows"

class UnifiedPipelineContracts(unittest.TestCase):
    def test_two_independent_main_workflows(self):
        s=(W/"sfdc-three-report-email-digestion.yml").read_text(encoding="utf-8")
        f=(W/"feishu-sources-unified.yml").read_text(encoding="utf-8")
        self.assertIn("on:",s)
        self.assertIn("on:",f)
        self.assertNotIn("  workflow_run:",s.split("permissions:")[0])
        self.assertNotIn("  workflow_run:",f.split("permissions:")[0])
        self.assertIn("python automation/sfdc/three_report_email_ingest.py",s)
        self.assertIn("python automation/sfdc/source_freshness_guard.py",s)
        self.assertIn("FEISHU_METRIC_SCOPE: quote",s)
        self.assertIn("FEISHU_METRIC_SCOPE: operations",f)
        self.assertIn("python3 automation/feishu/project_status_sync.py",f)
        self.assertIn("python3 automation/feishu/online_project_tat_forecast.py",f)
        self.assertIn("python3 automation/feishu/payment_reconciliation_qc.py",f)
        self.assertIn("python3 automation/feishu/monthly_revenue_actual_sync.py",f)
        self.assertNotIn("three_report_email_ingest.py",f)
        self.assertNotIn("source_freshness_guard.py",f)
        self.assertNotIn("set -e",s.lower()+" "+f.lower())
    def test_legacy_autoruns_are_disabled(self):
        for name in (
            "feishu-sales-metrics.yml",
            "feishu-canonical-monthly-revenue.yml",
            "feishu-online-project-tat.yml",
            "feishu-project-sync.yml",
            "sales-payment-reconciliation.yml",
            "feishu-native-sales-trends.yml",
            "feishu-native-payment-dashboard.yml",
        ):
            text=(W/name).read_text(encoding="utf-8")
            header=text.split("permissions:")[0]
            self.assertNotIn("  schedule:",header,name)
            self.assertNotIn("  workflow_run:",header,name)
    def test_payment_monthly_and_lifecycle_are_independent_jobs(self):
        s=(W/"feishu-sources-unified.yml").read_text(encoding="utf-8")
        self.assertIn("  ingest:\n    needs: tests",s)
        self.assertIn("  payment:\n    needs: ingest",s)
        self.assertIn("  monthly:",s)
        self.assertIn("    needs: [ingest, lifecycle]",s)
        self.assertIn("  lifecycle:\n    needs: ingest",s)
        self.assertNotIn("    needs: lifecycle",s)
        self.assertIn("LIFECYCLE_SOURCE_SHRINK_HOLD",
            (ROOT/"automation/css_mail/project_lifecycle_refresh.py").read_text(encoding="utf-8"))

    def test_scope_writes_are_disjoint(self):
        src=(ROOT/"automation/feishu/sales_metrics_sync.py").read_text(encoding="utf-8")
        self.assertIn('"quote":("Weekly Quote KPI",)',src)
        self.assertIn('"operations":("Project SIF Monitor",)',src)
        self.assertIn('if scope!="quote":',src)
        self.assertIn('if scope!="operations":',src)
        self.assertIn('"METRIC_SCOPE="+scope',src)

if __name__=="__main__":
    unittest.main()
