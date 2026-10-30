"""Deterministic tests of the Vercel path-to-workspace audit."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from vercel_deploy_scope import classify_paths, CSS, KALMAN, ROOT

MANIFEST = json.loads((ROOT / "package.json").read_text())


class DeployScopeTests(unittest.TestCase):
    def case(self, *files):
        return classify_paths(files, MANIFEST)

    def test_css_change_does_not_target_kalman(self):
        r = self.case("apps/css-sales-workspace/api/lifecycle.js",
                      "apps/css-sales-workspace/test/revenue-net-vat-contract.test.js")
        self.assertEqual(r["outcome"], "CSS_ONLY")
        self.assertTrue(r["css_web_changed"])
        self.assertFalse(r["kalman_web_changed"])
        self.assertFalse(r["vercel_deployment_verified"])

    def test_kalman_html_change_does_not_target_css(self):
        r = self.case("research/kalman_triple_barrier/web/index.html")
        self.assertEqual(r["outcome"], "KALMAN_ONLY")
        self.assertTrue(r["kalman_web_changed"])
        self.assertFalse(r["css_web_changed"])

    def test_non_web_pipelines_are_source_only(self):
        r = self.case("automation/css_mail/revenue_lifecycle_monthly.py",
                      ".github/workflows/css-revenue-net-vat.yml", "docs/notes.md")
        self.assertEqual(r["outcome"], "SOURCE_ONLY")
        self.assertFalse(r["css_web_changed"])
        self.assertFalse(r["kalman_web_changed"])

    def test_root_npm_changes_require_review(self):
        r = self.case("package-lock.json")
        self.assertEqual(r["outcome"], "GLOBAL_OR_UNSCOPED_REVIEW")
        self.assertIn("package-lock.json", r["root_global_files"])

    def test_outside_workspace_is_not_misreported_as_skipped(self):
        r = self.case("research/kalman_triple_barrier/engine.py")
        self.assertEqual(r["outcome"], "GLOBAL_OR_UNSCOPED_REVIEW")
        self.assertTrue(r["unscoped_files"])

    def test_both_web_apps_are_recorded(self):
        r = self.case(CSS + "/index.html", KALMAN + "/index.html")
        self.assertEqual(r["outcome"], "BOTH_WEB_APPS_CHANGED")

    def test_nested_workspace_configuration_rejected(self):
        m = dict(MANIFEST)
        m["workspaces"] = list(MANIFEST["workspaces"]) + ["research"]
        with self.assertRaisesRegex(ValueError, "Nested npm"):
            classify_paths(["docs/readme.md"], m)

    def test_parent_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.case("../secrets/thing")

if __name__ == "__main__":
    unittest.main()
