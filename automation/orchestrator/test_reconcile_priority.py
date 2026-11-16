"""Regression tests for sanitized revenue+CI evidence ranking; no external calls."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import priority
from reconcile_priority import validate_receipt, with_mirror_evidence


def receipt(status="MIRROR_3WAY_PARITY_AGED", **changes):
    obj = {
        "schema_version": 1,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "month": "2026-11",
        "source_scope": "GOOGLE_SHEETS_MIRROR_ONLY",
        "status": status,
        "source_tabs_checked": 3,
        "three_way_aggregate_parity": True,
        "snapshot_age_state": "AGED_RECHECK" if status.endswith("_AGED") else "WITHIN_REVIEW_THRESHOLD",
        "business_source_original_probed": False,
        "feishu_base_sink_readback_probed": False,
        "business_source_sink_verification": "NOT_VERIFIED",
        "no_business_writes": True,
    }
    obj.update(changes)
    return obj


def baseline(failure=False):
    policy = priority.load_policy()
    def fake(url, token):
        conclusion = "failure" if failure and "monthly-revenue" in url else "success"
        return {"workflow_runs": [{
            "id": 234, "head_branch": "main", "event": "schedule",
            "created_at": "2026-11-15T00:00:00Z",
            "status": "completed", "conclusion": conclusion,
        }]}
    return priority.build_priority(policy, fetch=fake)


def apply(evidence, *, failure=False):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "receipt.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        return with_mirror_evidence(baseline(failure=failure), path)


class JoinEvidenceTests(unittest.TestCase):
    def test_aged_revenue_ranks_first_even_when_ci_passed(self):
        result = apply(receipt())
        self.assertEqual("payment_revenue", result["next_review"]["domain"])
        self.assertEqual("MIRROR_3WAY_PARITY_AGED", result["revenue_mirror_evidence"])
        self.assertEqual("CI_SUCCESS_UNVERIFIED", result["next_review"]["signal"])
        self.assertIn("ORIGINAL_SOURCE", result["next_review"]["next_safe_action"])
        self.assertEqual("NOT_VERIFIED", result["business_source_sink_verification"])
        self.assertFalse(result["auto_execute_business_writes"])

    def test_recent_mirror_does_not_erase_old_ci_failure(self):
        result = apply(receipt("MIRROR_3WAY_PARITY_RECENT"), failure=True)
        self.assertEqual("CI_FAILED", result["next_review"]["signal"])
        self.assertIn("FAILED_REVENUE_CI", result["next_review"]["next_safe_action"])
        self.assertEqual("MIRROR_3WAY_PARITY_RECENT", result["revenue_mirror_evidence"])
        self.assertFalse(result["next_review"]["business_source_checked"])

    def test_report_only_does_not_fabricate_revenue_evidence(self):
        r = with_mirror_evidence(baseline(), None)
        self.assertEqual("MIRROR_NOT_COLLECTED_PR", r["revenue_mirror_evidence"])
        self.assertEqual(10, next(x for x in r["queue"] if x["domain"] == "payment_revenue")["priority"])

    def test_missing_receipt_triggers_read_only_review(self):
        r = with_mirror_evidence(baseline(), Path("/an/obviously/missing/autonext.json"))
        self.assertEqual("MIRROR_RECEIPT_MISSING", r["revenue_mirror_evidence"])
        self.assertEqual("payment_revenue", r["next_review"]["domain"])
        self.assertEqual("RESTORE_REVENUE_MIRROR_READONLY_EVIDENCE", r["next_review"]["next_safe_action"])

    def test_invalid_receipt_cannot_claim_verified_business(self):
        for changed in (
            {"business_source_sink_verification": "PASS"},
            {"business_source_original_probed": True},
            {"feishu_base_sink_readback_probed": True},
            {"source_scope": "QQ_ORIGINAL"},
            {"no_business_writes": False},
        ):
            with self.subTest(changed=changed):
                data = receipt(**changed)
                with self.assertRaises(ValueError):
                    validate_receipt(data)
                r = apply(data)
                self.assertEqual("MIRROR_RECEIPT_INVALID", r["revenue_mirror_evidence"])
                self.assertFalse(r["next_review"]["business_source_checked"])

    def test_parity_claim_without_three_tabs_or_age_proof_rejected(self):
        for changed in (
            {"source_tabs_checked": 2},
            {"three_way_aggregate_parity": False},
            {"snapshot_age_state": "WITHIN_REVIEW_THRESHOLD"},
        ):
            with self.assertRaises(ValueError):
                validate_receipt(receipt(**changed))

    def test_unknown_status_and_future_time_rejected(self):
        with self.assertRaises(ValueError):
            validate_receipt(receipt("PASS"))
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)).isoformat()
        with self.assertRaises(ValueError):
            validate_receipt(receipt(checked_at=future))

    def test_private_fields_are_never_copied_to_priority_artifact(self):
        report = apply(receipt(customer="sensitive", gross_krw=9999999,
                               invoice_id="confidential-ID"))
        serialized = json.dumps(report)
        self.assertNotIn("sensitive", serialized)
        self.assertNotIn("9999999", serialized)
        self.assertNotIn("confidential-ID", serialized)
        self.assertEqual("NOT_VERIFIED", report["business_source_sink_verification"])

    def test_unavailable_report_is_investigated_not_success(self):
        report = apply(receipt("MIRROR_UNAVAILABLE_OR_MISMATCH"))
        self.assertEqual("MIRROR_UNAVAILABLE_OR_MISMATCH", report["revenue_mirror_evidence"])
        self.assertEqual("payment_revenue", report["next_review"]["domain"])
        self.assertIn("DIAGNOSE", report["next_review"]["next_safe_action"])


if __name__ == "__main__":
    unittest.main()
