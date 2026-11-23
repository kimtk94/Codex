"""Safety checks for mirror-only evidence: never promote stale snapshots to PASS."""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from css_live_freshness_evidence import observe, month_gross_net, relative_snapshot_order

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 9, 1, 0, tzinfo=UTC)


def example():
    return {
        "Feishu Source Manifest": [
            ["Source", "Source Date", "Synced At KST", "Source ID", "Rows", "Schema", "Meaning"],
            ["Payment Outstanding", "2026-11-01", "2026-11-09T00:19:43+09:00", "4EPjYe", "314", "HEADER_MATCHED", "Snapshot"],
            ["eTax Invoice", "2026-10-31", "2026-11-09T00:19:43+09:00", "d9d7dG", "146", "HEADER_MATCHED", "Snapshot"],
            ["Payment Receipt", "2026-10-31", "2026-11-09T00:19:43+09:00", "2jUIBX", "495", "HEADER_MATCHED", "Snapshot"],
            ["Prepayments", "2026-10-31", "2026-11-09T00:19:43+09:00", "pc0bl4", "154", "HEADER_MATCHED", "Snapshot"],
            ["Online-Project", "2026-11-09", "2026-11-09T00:19:43+09:00", "project", "110", "BASE_FIELDS", "Snapshot"],
        ],
        "SFDC Email Ingest Audit": [
            ["Entity", "Source Received KST", "Ingest Checked KST", "Rows", "Unique IDs", "Duplicate IDs", "Missing IDs", "Content SHA256", "State", "Source Kind"],
            ["Leads", "2026-11-08 17:00:05 KST", "2026-11-09 00:35:01 KST", "515", "515", "0", "0", "hash", "PRESERVED_NO_NEW_REPORT", "QQ IMAP"],
            ["Opportunities", "2026-11-08 17:00:09 KST", "2026-11-09 00:35:01 KST", "706", "706", "0", "0", "hash", "PRESERVED_NO_NEW_REPORT", "QQ IMAP"],
            ["Quotation", "2026-11-08 17:00:07 KST", "2026-11-09 00:35:01 KST", "3883", "838", "3045", "0", "hash", "PRESERVED_NO_NEW_REPORT", "QQ IMAP"],
        ],
        "SFDC Report Readiness": [
            ["object", "records", "stable_id", "modified_timestamp", "required_field_check", "missing_fields", "promotion_status", "source"],
            ["SFDC Opportunity Raw", "332", "NO", "NO", "FAIL", "IDs", "HOLD - report export not verified", "snapshot"],
            ["Quotation", "23", "NO", "NO", "FAIL", "IDs", "HOLD - report export not verified", "snapshot"],
            ["SFDC Contacts", "187", "NO", "NO", "FAIL", "IDs", "HOLD - report export not verified", "snapshot"],
        ],
        "Revenue Source Authority": [
            ["Month", "Source Tab", "Source Role", "Issued Invoice Count", "Amount KRW", "Tax Basis", "Source Parity", "Authoritative For KPI", "Verified KST", "Required Action"],
            ["2026-11", "Life", "CANONICAL_ACTUAL_GROSS", "7", "49544550", "VAT_INCLUDED", "MATCHED", "YES", "date", "actual"],
            ["2026-11", "Net", "CANONICAL_ISSUED_NET", "7", "45040500", "VAT_EXCLUDED", "MATCHED", "YES", "date", "actual"],
        ],
        "BI Revenue Net VAT Monthly": [
            ["Month", "Gross", "Net", "kUSD", "Count", "Pending", "Forecast", "Verified", "Evidence"],
            ["2026-11", "49544550", "45040500", "30", "7", "10678250", "35239470", "date", "proof"],
        ],
        "BI Revenue Lifecycle Monthly": [
            ["Month", "Actual Invoice KRW", "Pending Verified KRW",
             "Forecast KRW", "Combined KRW (verified + estimate)",
             "Invoice Count", "Open Statement Count", "Pending Amount Unknown",
             "Forecast Projects", "Partial Billing Reviews", "Data Quality",
             "Snapshot KST"],
            ["2026-11", "₩49,544,550", "₩10,678,250", "₩35,239,470",
             "₩95,462,270", "7", "0", "0", "3", "0",
             "INVOICES_VERIFIED_FORECAST_ESTIMATE",
             "2026-11-09 09:00:00 KST"],
        ],
        "Automation Health": [
            ["Component", "Last success KST", "State", "Detail"],
            ["Feishu", "2026-10-24 13:46:32 KST", "PASS", "old run"],
            ["CSS Quotes", "2026-11-09 09:00:00 KST", "PASS", "recent run"],
            ["Quote Review", "2026-11-09 09:00:00 KST", "FAILED", "ignored"],
        ],
        "Payment Reconciliation QC": [
            ["Payment Reconciliation QC", "date", "READ_ONLY"],
            ["Metric", "Value", "Meaning"],
            ["Invoice-level verified paid count", "UNKNOWN", "Bank proof missing"],
        ],
        "Automation Workflow Runs": [
            ["Workflow", "Domain", "Run State", "Last Run UTC", "Age Hours", "GitHub Run URL", "Event", "Checked KST", "Verification Boundary", "Workflow File"],
            ["Feishu Payment", "Payment", "FAILED", "2026-11-08T00:00:00Z", "1.0", "url", "schedule", "date", "schema only", "feishu-payment-audit.yml"],
        ],
        "CSS Mail Backfill Status": [
            ["Updated At KST", "State", "QQ Staged Headers", "Web Cached UID", "Body Ready", "Body Empty MIME", "Header Pending", "Remaining Eligible", "Batch Selected", "Batch Body Fetched"],
            ["date", "WINDOW_CAUGHT_UP", "8826", "4530", "4176", "350", "0", "0", "0", "0"],
        ],
    }


class LiveEvidenceTests(unittest.TestCase):
    def test_nine_domains_eighteen_checks_never_fake_live_pass(self):
        d = observe(example(), NOW, target_month="2026-11")
        self.assertEqual(len(d["domains"]), 9)
        self.assertEqual(sum(len(item["checks"]) for item in d["domains"]), 18)
        self.assertTrue(d["mirror_only"])
        self.assertFalse(d["source_probed_live"])
        self.assertEqual(d["verified_crosschecks"], 0)
        for item in d["domains"]:
            self.assertEqual(item["status"], "BLOCK")
            self.assertEqual([c["axis"] for c in item["checks"]], ["source", "sink"])
            self.assertTrue(all(c["status"] == "BLOCK" for c in item["checks"]))
            self.assertTrue(all(c["source_probe_at"] is None and c["sink_readback_at"] is None
                                and c["gap_count"] is None for c in item["checks"]))

    def test_stale_etax_date_cannot_be_confused_with_fresh_sync_time(self):
        d = observe(example(), NOW, "2026-11")
        p = next(x for x in d["domains"] if x["id"] == "payment_revenue")
        self.assertEqual(p["checks"][0]["reason"], "ETAX_SNAPSHOT_MONTH_NOT_TARGET_MONTH")
        self.assertEqual(p["checks"][0]["snapshot"]["etax"]["source_date"], "2026-10-31")
        self.assertIn("2026-11-09", p["checks"][0]["snapshot"]["etax"]["mirror_sync_at"])

    def test_preserved_no_new_report_does_not_certify_no_new_data(self):
        d = observe(example(), NOW, "2026-11")
        p = next(x for x in d["domains"] if x["id"] == "quote")
        self.assertEqual(p["checks"][0]["snapshot"]["quotations"]["stage_state"],
                         "PRESERVED_NO_NEW_REPORT")
        self.assertEqual(p["checks"][1]["reason"], "SFDC_STAGING_NOT_VERIFIED_SAVED")
        self.assertEqual(p["status"], "BLOCK")

    def test_revenue_snapshot_parity_is_not_live_payment_proof(self):
        d = observe(example(), NOW, "2026-11")
        p = next(x for x in d["domains"] if x["id"] == "payment_revenue")
        self.assertTrue(p["checks"][1]["snapshot"]["monthly_snapshot"]["snapshot_amount_parity"])
        self.assertEqual(p["checks"][0]["snapshot"]["paid_invoice_proof"], "UNKNOWN")
        self.assertEqual(p["status"], "BLOCK")

    def test_snapshot_vat_mismatch_explicitly_blocks(self):
        data = example()
        data["Revenue Source Authority"][2][4] = "45040501"
        d = observe(data, NOW, "2026-11")
        p = next(x for x in d["domains"] if x["id"] == "payment_revenue")
        self.assertEqual(p["checks"][1]["reason"], "CANONICAL_REVENUE_SNAPSHOT_MISMATCH")

    def test_lifecycle_changed_since_net_snapshot_is_a_visible_hold(self):
        data = example()
        data["BI Revenue Lifecycle Monthly"][1][1] = "₩55,176,550"
        data["BI Revenue Lifecycle Monthly"][1][5] = "10"
        report = observe(data, NOW, "2026-11")
        result = report["snapshot_integrity"]["revenue"]
        self.assertFalse(result["snapshot_amount_parity"])
        self.assertEqual(result["invoice_count_delta_lifecycle_minus_net"], 3)
        self.assertTrue(result["lifecycle_gross_differs_from_net"])
        self.assertNotIn("55176550", str(report))
        self.assertNotIn("49544550", str(result))
        finance = next(x for x in report["domains"] if x["id"] == "payment_revenue")
        self.assertEqual(finance["checks"][1]["reason"],
                         "CANONICAL_REVENUE_SNAPSHOT_MISMATCH")
        self.assertEqual(finance["status"], "BLOCK")

    def test_revenue_snapshot_skew_shows_order_but_never_approves_write(self):
        data = example()
        data["BI Revenue Net VAT Monthly"][1][7] = "2026-11-23 10:00:00 KST"
        data["BI Revenue Lifecycle Monthly"][1][11] = "2026-11-23 14:00:00 KST"
        data["BI Revenue Lifecycle Monthly"][1][5] = "10"
        report = observe(data, NOW, "2026-11")
        snapshot = report["snapshot_integrity"]["revenue"]
        self.assertFalse(snapshot["snapshot_amount_parity"])
        self.assertEqual(snapshot["invoice_count_delta_lifecycle_minus_net"], 3)
        self.assertEqual(snapshot["snapshot_order"], "LIFECYCLE_NEWER_THAN_NET")
        self.assertTrue(snapshot["invoice_identity_review_required"])
        self.assertEqual(report["blocked_domains"], 9)
        self.assertFalse(report["source_probed_live"])
        self.assertFalse(report["sink_readback_live"])

    def test_revenue_order_requires_valid_full_kst_timestamps(self):
        self.assertEqual(relative_snapshot_order("2026-11-23 14:00:00 KST",
                                                 "2026-11-23 10:00:00 KST"),
                         "NET_NEWER_THAN_LIFECYCLE")
        self.assertEqual(relative_snapshot_order("2026-11-23 10:00:00 KST",
                                                 "2026-11-23 10:00:00 KST"),
                         "SAME_TIMESTAMP")
        self.assertEqual(relative_snapshot_order("updated today",
                                                 "2026-11-23 10:00:00 KST"),
                         "UNVERIFIED_TIMESTAMPS")
        self.assertEqual(relative_snapshot_order("2026-11-23 10:00:00",
                                                 "2026-11-23 10:00:00 KST"),
                         "UNVERIFIED_TIMESTAMPS")

    def test_stale_legacy_health_pass_is_not_a_live_green(self):
        report = observe(example(), NOW, "2026-11")
        health = report["snapshot_integrity"]["legacy_health"]
        self.assertEqual(health["legacy_green_rows"], 2)
        self.assertEqual(health["stale_green_rows"], 1)
        self.assertEqual(health["unknown_timestamp_green_rows"], 0)
        self.assertFalse(health["legacy_green_is_current_proof"])
        monitor = next(x for x in report["domains"] if x["id"] == "monitor")
        self.assertEqual(monitor["checks"][0]["reason"],
                         "LEGACY_HEALTH_GREEN_STATUS_NOT_CURRENT")
        self.assertEqual(monitor["status"], "BLOCK")

    def test_undated_legacy_pass_never_becomes_current(self):
        data = example()
        data["Automation Health"][2][1] = "2026-11-09 (manual audit)"
        report = observe(data, NOW, "2026-11")
        health = report["snapshot_integrity"]["legacy_health"]
        self.assertEqual(health["unknown_timestamp_green_rows"], 1)
        self.assertFalse(health["legacy_green_is_current_proof"])

    def test_noninteger_money_and_missing_lifecycle_fail_closed(self):
        data = example()
        data["BI Revenue Lifecycle Monthly"][1][1] = "₩49,544,550.50"
        with self.assertRaisesRegex(ValueError, "REVENUE_MIRROR_AMOUNT_INVALID"):
            observe(data, NOW, "2026-11")
        data = example()
        data.pop("BI Revenue Lifecycle Monthly")
        with self.assertRaisesRegex(ValueError, "MIRROR_TAB_MISSING_OR_TRUNCATED"):
            observe(data, NOW, "2026-11")

    def test_missing_source_tab_never_becomes_zero_new_data(self):
        data = example()
        data.pop("Feishu Source Manifest")
        with self.assertRaisesRegex(ValueError, "MIRROR_TAB_MISSING_OR_TRUNCATED"):
            observe(data, NOW, "2026-11")

    def test_duplicate_source_key_blocks_ambiguous_manifest(self):
        data = example()
        data["Feishu Source Manifest"].append(data["Feishu Source Manifest"][2][:])
        with self.assertRaisesRegex(ValueError, "MIRROR_KEY_MISSING_OR_DUPLICATE"):
            observe(data, NOW, "2026-11")


if __name__ == "__main__":
    unittest.main()
