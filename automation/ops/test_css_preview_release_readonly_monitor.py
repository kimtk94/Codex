import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("css_preview_release_readonly_monitor.py")
spec = importlib.util.spec_from_file_location("css_preview_release_readonly_monitor", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
SHA = "a" * 40
HEADER = ["Area", "Check", "Result", "Gate", "Evidence KST", "Observed",
          "Next action", "Checked KST"]


def fixtures():
    pr = {"number": 487, "state": "open", "head": {"sha": SHA}}
    project = {"ssoProtection": {"deploymentType": "all_except_custom_domains"}}
    deployments = {"deployments": [
        {"target": None, "state": "READY", "url": "css-preview-test.vercel.app",
         "created": 10, "meta": {"githubCommitSha": SHA}},
        {"target": "production", "state": "READY", "url": "css-production.vercel.app",
         "created": 100, "meta": {"githubCommitSha": SHA}}
    ]}
    ledger = {"values": [HEADER] + [
        ["Release", c, "BLOCK", "RELEASE", "", "", "", ""]
        for c in mod.RELEASE]}
    return pr, project, deployments, ledger


class TestPreviewReleaseMonitor(unittest.TestCase):
    def test_ready_preview_is_not_approval(self):
        out = mod.evaluate(*fixtures())
        self.assertEqual(out["state"], "READY_FOR_OWNER_OAUTH_E2E")
        self.assertTrue(out["exact_sha_preview_ready"])
        self.assertEqual(out["pr_sha_prefix"], SHA[:12])
        self.assertEqual(out["acceptance_release_states"],
                         dict.fromkeys(mod.RELEASE, "BLOCK"))
        self.assertFalse(out["production_approval"])
        self.assertFalse(out["production_deploy"])
        self.assertEqual(out["owner_authenticated_browser_e2e"],
                         "NOT_VERIFIED_BY_THIS_AUDIT")
        self.assertEqual(out["preview_url"], "https://css-preview-test.vercel.app")

    def test_stale_preview_sha_blocks(self):
        args = fixtures()
        args[2]["deployments"][0]["meta"]["githubCommitSha"] = "b" * 40
        out = mod.evaluate(*args)
        self.assertEqual(out["state"], "BLOCK_READINESS")
        self.assertFalse(out["exact_sha_preview_ready"])

    def test_production_must_never_satisfy_preview_requirement(self):
        args = fixtures()
        args[2]["deployments"] = [args[2]["deployments"][1]]
        self.assertFalse(mod.evaluate(*args)["exact_sha_preview_ready"])

    def test_unprotected_deployment_blocks(self):
        args = fixtures()
        args[1]["ssoProtection"] = None
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")
        args = fixtures()
        args[1]["ssoProtection"]["enabled"] = False
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")
        args = fixtures()
        args[1]["ssoProtection"]["deploymentType"] = "none"
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")

    def test_native_vercel_api_mode_without_normalized_enabled_is_protected(self):
        args = fixtures()
        # Exact raw GET format has deploymentType, but no enabled property.
        self.assertNotIn("enabled", args[1]["ssoProtection"])
        self.assertEqual(mod.evaluate(*args)["state"], "READY_FOR_OWNER_OAUTH_E2E")
        for mode in ("preview", "all", "prod_deployment_urls_and_all_previews"):
            args[1]["ssoProtection"]["deploymentType"] = mode
            self.assertTrue(mod.evaluate(*args)["vercel_sso_enabled"])

    def test_missing_or_duplicate_ledger_release_rows_block(self):
        args = fixtures()
        args[3]["values"].pop()
        self.assertFalse(mod.evaluate(*args)["acceptance_ledger_schema_valid"])
        args = fixtures()
        args[3]["values"].append(args[3]["values"][1].copy())
        self.assertFalse(mod.evaluate(*args)["acceptance_ledger_schema_valid"])

    def test_wrong_pr_state_or_malicious_host_blocks(self):
        args = fixtures()
        args[0]["state"] = "closed"
        self.assertEqual(mod.evaluate(*args)["state"], "BLOCK_READINESS")
        args = fixtures()
        args[2]["deployments"][0]["url"] = "css-preview-test.vercel.app/steal"
        out = mod.evaluate(*args)
        self.assertEqual(out["state"], "BLOCK_READINESS")
        self.assertEqual(out["preview_url"], "")

    def test_release_ledger_pass_never_authorizes_production(self):
        args = fixtures()
        for row in args[3]["values"][1:]:
            row[2] = "PASS"
        out = mod.evaluate(*args)
        self.assertFalse(out["production_approval"])
        self.assertEqual(out["owner_authenticated_browser_e2e"],
                         "NOT_VERIFIED_BY_THIS_AUDIT")


    def source_batch(self):
        date = "2026-11-02"
        stamp = date + " 12:10:00 KST"
        header = ["AMEA", "Project / Institution", "Watch Quote KRW", "Watch X (unsafe)",
                  "Online H Candidate", "Online X Candidate", "Online Stage Candidate",
                  "Finance Base X Candidate", "Evidence State"]
        cross_row = ["AMEA2026090309", "Synthetic Project", "", "", "", "",
                     "", "X209SC26107211", "FINANCE_AMEA_CANDIDATE"]
        cross_row += [""] * 9 + [stamp, "test-run"]
        net_head = ["Month", "Issued Invoice Gross KRW (VAT incl)",
                    "Issued Net Revenue KRW (VAT excl)"]
        net_row = ["2026-11", "0", "0", "0", "0", "0", "75282495",
                   stamp, "INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"]
        mail_head = ["Updated At KST", "State", "QQ Staged Headers",
                     "Web Cached UID", "Body Ready"]
        mail_row = [stamp, "WINDOW_CAUGHT_UP", "7965", "3945", "3676"]
        return {"valueRanges": [
            {"values": [header, cross_row]},
            {"values": [net_head, net_row]},
            {"values": [mail_head, mail_row]},
            {"values": [["Source", "Source Date"],
                        ["Payment Outstanding", "2026-10-26"]]}
        ]}

    def test_source_prerequisites_fresh_with_old_payment_kept_review_only(self):
        from datetime import datetime, timezone
        when = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)
        result = mod.inspect_sources(self.source_batch(), when)
        self.assertTrue(result["ready"])
        self.assertEqual(result["crosswalk_rows"], 1)
        self.assertEqual(result["mail_body_ready"], 3676)
        self.assertTrue(result["finance_source_stale_review"])
        self.assertEqual(result["finance_source_age_days"], 7)
        self.assertFalse(result["contract_approved"])
        self.assertFalse(result["payment_approved"])
        pre = mod.evaluate(*fixtures(), result)
        self.assertEqual(pre["state"], "READY_FOR_OWNER_OAUTH_E2E_WITH_FINANCE_REVIEW")
        self.assertEqual(result["reason"],
                         "SOURCE_PREREQUISITES_READY_FINANCE_REVIEW_REQUIRED")
        self.assertEqual(result["finance_decision_gate"], "STALE_REVIEW_ONLY")
        self.assertFalse(pre["production_approval"])

    def test_fresh_payment_source_means_current_date_not_payment_proof(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][3]["values"][1][1] = "2026-11-02"
        now = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)
        current = mod.inspect_sources(batch, now)
        self.assertTrue(current["ready"])
        self.assertFalse(current["finance_source_stale_review"])
        self.assertEqual(current["finance_source_age_days"], 0)
        self.assertEqual(current["finance_decision_gate"],
                         "SOURCE_DATE_CURRENT_NOT_PAYMENT_APPROVAL")
        self.assertEqual(current["reason"], "SOURCE_PREREQUISITES_FRESH")
        evaluated = mod.evaluate(*fixtures(), current)
        self.assertEqual(evaluated["state"], "READY_FOR_OWNER_OAUTH_E2E")
        self.assertFalse(evaluated["production_approval"])
        self.assertFalse(current["payment_approved"])

    def test_five_day_old_finance_source_warns_without_promoting(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][3]["values"][1][1] = "2026-10-28"
        now = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)
        current = mod.inspect_sources(batch, now)
        self.assertTrue(current["ready"])
        self.assertTrue(current["finance_source_stale_review"])
        self.assertEqual(current["finance_source_age_days"], 5)
        self.assertEqual(mod.evaluate(*fixtures(), current)["state"],
                         "READY_FOR_OWNER_OAUTH_E2E_WITH_FINANCE_REVIEW")
        self.assertFalse(current["contract_approved"])

    def test_expired_contract_snapshot_fails_closed(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][0]["values"][1][18] = "2026-10-29 12:10:00 KST"
        result = mod.inspect_sources(batch, datetime(2026, 11, 2, 3, 30,
                                                      tzinfo=timezone.utc))
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "CONTRACT_GENERATED_SNAPSHOT_STALE")
        self.assertEqual(mod.evaluate(*fixtures(), result)["state"], "BLOCK_READINESS")

    def test_future_contract_snapshot_fails_closed(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][0]["values"][1][18] = "2026-11-03 12:10:00 KST"
        result = mod.inspect_sources(batch, datetime(2026, 11, 2, 3, 30,
                                                      tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "CONTRACT_GENERATED_SNAPSHOT_STALE")

    def test_duplicate_amea_fails_closed(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][0]["values"].append(
            batch["valueRanges"][0]["values"][1].copy())
        result = mod.inspect_sources(batch, datetime(2026, 11, 2, 3, 30,
                                                      tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "CONTRACT_CROSSWALK_INVALID")

    def test_stale_net_and_absent_november_fail_closed(self):
        from datetime import datetime, timezone
        when = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)
        batch = self.source_batch()
        batch["valueRanges"][1]["values"][1][7] = "2026-10-20 12:10:00 KST"
        self.assertEqual(mod.inspect_sources(batch, when)["reason"],
                         "NET_REVENUE_SNAPSHOT_STALE")
        batch = self.source_batch()
        batch["valueRanges"][1]["values"][1][0] = "2026-10"
        self.assertEqual(mod.inspect_sources(batch, when)["reason"],
                         "NET_REVENUE_CURRENT_MONTH_MISSING")

    def test_missing_mail_body_fails_closed(self):
        from datetime import datetime, timezone
        batch = self.source_batch()
        batch["valueRanges"][2]["values"][1][4] = "0"
        result = mod.inspect_sources(batch, datetime(2026, 11, 2, 3, 30,
                                                      tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "MAIL_BODY_NOT_AVAILABLE")

    def test_payment_manifest_does_not_infer_receipts(self):
        from datetime import datetime, timezone
        when = datetime(2026, 11, 2, 3, 30, tzinfo=timezone.utc)
        batch = self.source_batch()
        batch["valueRanges"][3]["values"][1][1] = "2026-11-03"
        self.assertEqual(mod.inspect_sources(batch, when)["reason"],
                         "PAYMENT_OUTSTANDING_DATE_FUTURE")
        batch = self.source_batch()
        batch["valueRanges"][3]["values"].pop()
        self.assertEqual(mod.inspect_sources(batch, when)["reason"],
                         "PAYMENT_MANIFEST_MISSING")
        batch = self.source_batch()
        batch["valueRanges"][3]["values"][1][0] = "eTax Invoice"
        self.assertEqual(mod.inspect_sources(batch, when)["reason"],
                         "PAYMENT_OUTSTANDING_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
