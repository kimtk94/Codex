"""Offline CSS Vercel Git branch allowlist tests.

This checks intended policy samples; live Vercel behavior still needs API
verification and a protected CSS preview receipt.
"""
import fnmatch
import json
from pathlib import Path
import unittest

CONFIG=Path(__file__).resolve().parents[2]/"apps"/"css-sales-workspace"/"vercel.json"

def enabled(branch, rules):
    matches=[value for pattern,value in rules.items() if fnmatch.fnmatchcase(branch,pattern)]
    return any(matches) if matches else True

class CssGitDeploymentTests(unittest.TestCase):
    def config(self):
        doc=json.loads(CONFIG.read_text(encoding="utf-8"))
        return doc,doc["git"]["deploymentEnabled"]

    def test_research_hcc_kalman_branches_disabled(self):
        _,rules=self.config()
        for branch in ("feat/hcc-public-ci-20261022","research-status",
                       "feat/kalman-triple-barrier","fix/kalman-ledger-main",
                       "research/upbit-2026","feat/radiomics-rnaseq",
                       "audit/external-data-2026"):
            with self.subTest(branch=branch):
                self.assertFalse(enabled(branch,rules))

    def test_css_sales_and_sfdc_preview_branches_allowed(self):
        _,rules=self.config()
        for branch in ("feat/css-vercel-branch-allowlist-20261031",
                       "fix/css-qq-freshness","feat/sfdc-playwright-desktop-p0",
                       "fix/sfdc-report-duplicate","feat/sales-dashboard",
                       "fix/vercel-separate-css-kalman-workspaces",
                       "feat/novogene-automation"):
            with self.subTest(branch=branch):
                self.assertTrue(enabled(branch,rules))
        self.assertFalse(enabled("main",rules),"GitHub main must never auto-deploy CSS Production")

    def test_all_other_branches_deny_by_default_and_no_positive_overlap(self):
        _,rules=self.config()
        for branch in ("research-status","feat/hcc-public-ci-20261022",
                       "feat/kalman-usdkrw-fred-qc-gate-20261031",
                       "release/production","main","feat/arbitrary-ui",
                       "feat/invoice-unreviewed","hotfix/unknown"):
            with self.subTest(branch=branch):
                self.assertFalse(enabled(branch,rules))
        for branch in ("feat/css-policy-preview","fix/sales-frontend",
                       "feat/sfdc-oppo-web","fix/novogene-portal"):
            with self.subTest(branch=branch):
                self.assertTrue(enabled(branch,rules))

    def test_no_deployment_bypass_or_sso_changes(self):
        doc,rules=self.config()
        self.assertIs(rules.get("**"),False)
        self.assertIs(rules.get("main"),False)
        self.assertNotIn("ignoreCommand",doc)
        self.assertNotIn("passwordProtection",doc)
        self.assertNotIn("ssoProtection",doc)
        self.assertNotIn("deploymentPolicy",doc)

if __name__=="__main__":
    unittest.main()
