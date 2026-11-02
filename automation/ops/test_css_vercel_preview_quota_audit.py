import importlib.util
import unittest
from pathlib import Path

p = Path(__file__).with_name("css_vercel_preview_quota_audit.py")
spec = importlib.util.spec_from_file_location("css_vercel_preview_quota_audit", p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def mock():
    return {name: {"id": pid, "accountId": module.TEAM,
                   "previewDeploymentsDisabled": True,
                   "ssoProtection": {"deploymentType": "all_except_custom_domains"}}
            for name, pid in module.PROJECTS.items()}


class TestVercelPreviewQuotaAudit(unittest.TestCase):
    def test_disabled_on_three_correct_projects(self):
        states, ok = module.validate_projects(mock())
        self.assertTrue(ok)
        self.assertEqual(set(states), set(module.PROJECTS))

    def test_single_enabled_preview_fails_closed(self):
        data = mock()
        data["CSS"]["previewDeploymentsDisabled"] = False
        states, ok = module.validate_projects(data)
        self.assertFalse(ok)
        self.assertIs(states["CSS"]["preview_deployments_disabled"], False)

    def test_missing_flag_is_not_implicitly_disabled(self):
        data = mock()
        data["Kalman Hub"].pop("previewDeploymentsDisabled")
        states, ok = module.validate_projects(data)
        self.assertFalse(ok)
        self.assertEqual(states["Kalman Hub"]["preview_deployments_disabled"], "UNKNOWN")

    def test_wrong_project_or_account_fails(self):
        data = mock()
        data["CSS"]["id"] = "prj_other"
        self.assertFalse(module.validate_projects(data)[1])
        data = mock()
        data["CSS"]["accountId"] = "team_other"
        self.assertFalse(module.validate_projects(data)[1])

    def test_missing_sso_protection_fails(self):
        data = mock()
        data["Kalman Lab"]["ssoProtection"] = None
        self.assertFalse(module.validate_projects(data)[1])

    def test_rolling_window_includes_error_and_cancelled(self):
        d = [{"id": "a", "created": 100, "state": "ERROR", "name": "CSS"},
             {"id": "b", "created": 200, "state": "CANCELED", "name": "Kalman"},
             {"id": "c", "created": 300, "state": "READY", "name": "Kalman"},
             {"id": "d", "created": 10, "state": "READY", "name": "other"}]
        out = module.classify_usage(d, 50, 300)
        self.assertEqual(out["total_attempt_records"], 3)
        self.assertEqual(out["state_counts"],
                         {"CANCELED": 1, "ERROR": 1, "READY": 1})
        self.assertFalse(out["exceeds_100_record_reference"])
        self.assertTrue(out["count_is_not_authoritative_quota_charge"])

    def test_records_at_quota_do_not_authorize_deploy(self):
        d = [{"id": str(i), "created": i+1, "state": "CANCELED",
              "name": "CSS"} for i in range(100)]
        out = module.classify_usage(d, 1, 101)
        self.assertTrue(out["exceeds_100_record_reference"])


if __name__ == "__main__":
    unittest.main()
