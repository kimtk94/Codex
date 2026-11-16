"""Offline regression for bounded one-next GitHub CI failure triage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import next_investigation as next_one
import priority


def fake_queue(failed_domain="payment_revenue", overridden=None):
    def fetch(url, token):
        state = "failure" if failed_domain in url else "success"
        return {"workflow_runs": [
            {"id": 43169186939 if state == "failure" else 100,
             "head_branch": "main", "event": "workflow_dispatch",
             "created_at": "2026-11-16T10:00:00Z",
             "status": "completed", "conclusion": state},
        ]}
    report = priority.build_priority(priority.load_policy(), fetch=fetch)
    if overridden:
        report["next_review"].update(overridden)
    return report


def jobs(*items):
    return {"jobs": list(items)}


class BoundedFailedJobInspectionTests(unittest.TestCase):
    def test_exact_canonical_failure_code_and_not_raw_amounts(self):
        doc = fake_queue()
        seen = []
        def fjob(run_id, token):
            seen.append(("jobs", run_id))
            return jobs({"id": 11, "conclusion": "success"},
                        {"id": 22, "conclusion": "failure"})
        def flog(job_id, token):
            seen.append(("log", job_id))
            return ("MONTHLY_CANONICAL_FAILED:MONTHLY_AUTHORITY_FAIL_CLOSED:"
                    "CANONICAL_LIFECYCLE_GROSS_COUNT_MISMATCH "
                    "issued_gross_krw=76277300 lifecycle_gross_krw=76538550")
        r = next_one.investigate(doc, fetch_jobs=fjob, fetch_log=flog, token="test")
        self.assertEqual("FAILED_JOB_DIAGNOSTIC_FOUND", r["state"])
        self.assertEqual("REVENUE_ISSUED_VS_LIFECYCLE_MISMATCH", r["diagnostic_code"])
        self.assertEqual([("jobs", 43169186939), ("log", 22)], seen)
        self.assertEqual("NOT_VERIFIED", r["business_source_sink_verification"])
        self.assertFalse(r["auto_retry_runs"])
        self.assertNotIn("76277300", json.dumps(r))
        self.assertNotIn("76538550", json.dumps(r))

    def test_not_selected_log_action_never_fetches(self):
        doc = fake_queue(overridden={"next_safe_action": "RESTORE_QQ_ORIGINAL_PROBE"})
        with patch.object(next_one, "read_jobs", side_effect=AssertionError("not allowed")):
            r = next_one.investigate(doc, fetch_jobs=lambda *a: 1)
        self.assertEqual("NOT_APPLICABLE", r["state"])

    def test_untrusted_run_id_fails_closed(self):
        for overridden in ({"run_id": -1}, {"run_id": "22"},
                           {"workflow": "evil.yml"},
                           {"run_url": "https://evil.invalid/log"}):
            with self.subTest(overridden=overridden):
                r = next_one.investigate(fake_queue(overridden=overridden),
                                          fetch_jobs=lambda *a: 1)
                self.assertEqual("INVALID_PRIORITIZATION", r["state"])

    def test_priority_state_cannot_claim_business_pass(self):
        doc = fake_queue()
        doc["business_source_sink_verification"] = "PASS"
        self.assertEqual("INVALID_PRIORITIZATION",
                         next_one.investigate(doc, fetch_jobs=lambda *a: None)["state"])
        doc = fake_queue()
        doc["auto_merge_pr"] = True
        self.assertEqual("INVALID_PRIORITIZATION",
                         next_one.investigate(doc, fetch_jobs=lambda *a: None)["state"])

    def test_failed_run_without_failed_job_is_indeterminate(self):
        r = next_one.investigate(fake_queue(), fetch_jobs=lambda *a: jobs({"id": 1, "conclusion": "success"}))
        self.assertEqual("FAILED_RUN_NO_FAILED_JOB", r["state"])
        self.assertIsNone(r["diagnostic_code"])

    def test_log_unavailable_is_not_diagnostic_success(self):
        r = next_one.investigate(
            fake_queue(),
            fetch_jobs=lambda *a: jobs({"id": 22, "conclusion": "failure"}),
            fetch_log=lambda *a: (_ for _ in ()).throw(OSError("secret from private log")))
        self.assertEqual("FAILED_JOB_LOG_UNAVAILABLE", r["state"])
        self.assertNotIn("secret from private log", json.dumps(r))

    def test_api_error_is_distinct_from_no_failed_job(self):
        r = next_one.investigate(fake_queue(), fetch_jobs=lambda *a: (_ for _ in ()).throw(OSError("denied")))
        self.assertEqual("FAILED_RUN_FETCH_UNAVAILABLE", r["state"])
        self.assertEqual(0, r["inspected_failed_jobs"])

    def test_maximum_three_failed_logs_scanned(self):
        seen = []
        r = next_one.investigate(
            fake_queue(),
            fetch_jobs=lambda *a: jobs(*[{"id": i, "conclusion": "failure"} for i in range(1, 10)]),
            fetch_log=lambda job, token: seen.append(job) or "no whitelisted diagnostic")
        self.assertEqual("FAILED_JOB_UNCLASSIFIED", r["state"])
        self.assertEqual([1, 2, 3], seen)
        self.assertEqual(3, r["inspected_failed_jobs"])

    def test_receipt_never_contains_real_logs(self):
        r = next_one.investigate(
            fake_queue(),
            fetch_jobs=lambda *a: jobs({"id": 22, "conclusion": "failure"}),
            fetch_log=lambda *a: "PRIVATE_CUSTOMER_EMAIL contact@example.com\nHTTP Error 403")
        self.assertEqual("SOURCE_ACCESS_FORBIDDEN", r["diagnostic_code"])
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "result.json"
            next_one.write_receipt(r, path)
            payload = path.read_text()
            self.assertNotIn("contact@example.com", payload)
            self.assertFalse(json.loads(payload)["raw_logs_persisted"])

    def test_malformed_priority_is_not_processed(self):
        for malformed in ({}, {"next_review": "anything"}, {"queue": []}):
            self.assertEqual("INVALID_PRIORITIZATION", next_one.investigate(malformed)["state"])

    def test_log_reader_rejects_unsafe_url_before_download(self):
        with self.assertRaises(ValueError):
            next_one.req("https://malicious.invalid/actions/runs/1/jobs", "dummy")


if __name__ == "__main__":
    unittest.main()
