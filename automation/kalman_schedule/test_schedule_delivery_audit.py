"""Delivery count evidence is not seal proof; exercise all failure branches."""
import unittest
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from schedule_delivery_audit import audit, latest_due_day, WORKFLOWS


def clock(day=24, hour=10, minute=30):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def fake_api(*, count=(2, 2), state=("active", "active"),
             wrong_event=False, incomplete=False, duplicate=False, running=False):
    def get(path):
        if "/runs?" not in path:
            filename = path.split("/")[-1]
            idx = WORKFLOWS.index(filename)
            return {"id": 101 + idx, "path": ".github/workflows/" + filename,
                    "state": state[idx]}
        parsed = urlparse(path)
        idx = int(parsed.path.split("/")[-2]) - 101
        day = parse_qs(parsed.query)["created"][0]
        runs = [
            {"id": 1000 + idx * 100 + (0 if duplicate else i),
             "workflow_id": 101 + idx, "event": "push" if wrong_event else "schedule",
             "head_branch": "main", "created_at": f"{day}T04:15:00Z",
             "status": "in_progress" if running else "completed",
             "conclusion": None if running else "success", "head_sha": "abc"}
            for i in range(count[idx])
        ]
        return {"total_count": len(runs) + int(incomplete), "workflow_runs": runs}
    return get


class DeliveryAuditTests(unittest.TestCase):
    def test_four_deliveries_not_seal_proof(self):
        report = audit(clock(), fake_api())
        self.assertEqual(report["status"], "DELIVERY_COUNT_OK_NOT_SEAL_PROOF")
        self.assertEqual(report["observed_schedule_deliveries"], 4)
        self.assertFalse(report["original_first_and_replay_roles_verified"])
        self.assertEqual(report["scientific_approval"], "HOLD")
        self.assertFalse(report["independent_off_github_monitor"])

    def test_all_four_absent_fails(self):
        report = audit(clock(), fake_api(count=(0, 0)))
        self.assertEqual(report["status"], "SCHEDULE_DELIVERY_HOLD")
        self.assertEqual(report["observed_schedule_deliveries"], 0)
        self.assertEqual(len(report["problem_codes"]), 2)

    def test_disabled_and_incomplete_workflow(self):
        report = audit(clock(), fake_api(count=(0, 2),
                      state=("disabled_manually", "active"), running=True))
        self.assertEqual(report["status"], "SCHEDULE_DELIVERY_HOLD")
        self.assertIn("WORKFLOW_NOT_ACTIVE",
                      [p["code"] for p in report["problem_codes"]])
        self.assertIn("SCHEDULE_RUN_INCOMPLETE_OR_UNSUCCESSFUL",
                      [p["code"] for p in report["problem_codes"]])

    def test_wrong_event_duplicate_and_partial_listing_unavailable(self):
        for kwargs in [{"wrong_event": True}, {"duplicate": True}, {"incomplete": True}]:
            with self.subTest(kwargs=kwargs):
                report = audit(clock(), fake_api(**kwargs))
                self.assertEqual(report["status"], "API_EVIDENCE_UNAVAILABLE_HOLD")
                self.assertIsNone(report["observed_schedule_deliveries"])

    def test_excess_run_count_cannot_pass(self):
        report = audit(clock(), fake_api(count=(3, 2)))
        self.assertEqual(report["status"], "SCHEDULE_DELIVERY_HOLD")

    def test_audit_after_cutoff_and_skip_unscheduled_days(self):
        self.assertEqual(str(latest_due_day(clock(25, 8, 14))), "2026-11-24")
        self.assertEqual(str(latest_due_day(clock(25, 8, 15))), "2026-11-25")
        self.assertEqual(str(latest_due_day(clock(30, 12))), "2026-11-28")
        with self.assertRaises(ValueError):
            latest_due_day(clock(24, 7))

    def test_api_error_is_not_zero_or_success(self):
        def denied(path):
            raise OSError("secret raw response must not be emitted")
        report = audit(clock(), denied)
        self.assertEqual(report["status"], "API_EVIDENCE_UNAVAILABLE_HOLD")
        self.assertFalse(report["api_evidence_complete"])
        self.assertIsNone(report["observed_schedule_deliveries"])
        self.assertNotIn("secret", str(report))


if __name__ == "__main__":
    unittest.main()
