"""Fail-closed contracts for the one-time actual-clock recovery dispatcher."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, parse_qs

from recovery_dispatch import (
    decide, verify_recovery_clock, load_request, VERSION, WORKFLOW_ID, ACTIVE_STATES
)


def clock(hour=11, minute=0, day=24):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


REQUEST = {
    "version": VERSION, "classification": "ACTUAL_TIME_MANUAL_RESEARCH_RECOVERY",
    "research_only": True, "live_execution": False, "production_writes": False,
    "scheduled_seal_credit": False, "historical_reseal": False,
    "requested_role": "FIRST_IF_ABSENT", "incident": 1045,
    "session": "2026-11-23", "target_utc_day": "2026-11-24",
}


def row(run_id=10, event="push", status="completed", conclusion="failure"):
    return {"id": run_id, "workflow_id": WORKFLOW_ID, "head_branch": "main",
            "event": event, "status": status, "conclusion": conclusion,
            "created_at": "2026-11-24T10:40:00Z"}


def fake_api(runs=(), active=(), state="active", bad_total=False):
    def get(path):
        if "/runs?" not in path:
            return {"id": WORKFLOW_ID,
                    "path": ".github/workflows/kalman-daily20.yml", "state": state}
        q = parse_qs(urlparse(path).query)
        if "status" in q:
            selected = [r for r in active if r["status"] == q["status"][0]]
        else:
            selected = list(runs)
        return {"total_count": len(selected) + (1 if bad_total else 0),
                "workflow_runs": selected}
    return get


class RecoveryDispatchContract(unittest.TestCase):
    def test_eligible_with_failed_main_push_only(self):
        report = decide(REQUEST, clock(), fake_api([row()]))
        self.assertEqual(report["status"], "RECOVERY_DISPATCH_ELIGIBLE")
        self.assertFalse(report["scheduled_seal_credit"])
        self.assertFalse(report["dispatch_accepted"])
        self.assertFalse(report["historical_reseal"])
        self.assertEqual(report["requested_event"], "workflow_dispatch")

    def test_existing_scheduled_or_manual_event_blocks_even_on_failure(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                report = decide(REQUEST, clock(), fake_api([row(event=event)]))
                self.assertIn("ORIGINAL_SCHEDULE_OR_MANUAL_EVENT_ALREADY_EXISTS",
                              report["blockers"])

    def test_successful_main_run_blocks(self):
        report = decide(REQUEST, clock(), fake_api([row(conclusion="success")]))
        self.assertIn("SUCCESSFUL_MAIN_RUN_REQUIRES_REVIEW", report["blockers"])

    def test_active_main_run_blocks_even_from_other_day(self):
        old = row(status="queued", conclusion=None)
        old["created_at"] = "2026-11-23T23:00:00Z"
        report = decide(REQUEST, clock(), fake_api(active=[old]))
        self.assertEqual(report["blockers"], ["MAIN_RESEARCH_RUN_ACTIVE"])

    def test_duplicate_unverified_or_incomplete_listing_fails(self):
        invalid = row()
        invalid["workflow_id"] = 8
        for api in (fake_api([row(), row()]), fake_api([invalid]),
                    fake_api([row()], bad_total=True)):
            with self.assertRaises(ValueError):
                decide(REQUEST, clock(), api)

    def test_inactive_target_fails(self):
        with self.assertRaisesRegex(ValueError, "WORKFLOW_NOT_VERIFIED_ACTIVE"):
            decide(REQUEST, clock(), fake_api(state="disabled_manually"))

    def test_stale_wrong_or_late_session_fails(self):
        for session, day, now, minutes in (
                ("2026-11-23", "2026-11-24", clock(7), 0),
                ("2026-11-23", "2026-11-24", clock(12, 30), 120),
                ("2026-11-23", "2026-11-24", clock(14, 30), 0),
                ("2026-11-23", "2026-11-24", clock(day=25), 0),
                ("2026-11-20", "2026-11-24", clock(), 0),
                ("2026-11-25", "2026-11-27", clock(day=27), 0)):
            with self.subTest(session=session, day=day, now=now):
                with self.assertRaises(ValueError):
                    verify_recovery_clock(session, day, now, min_minutes=minutes)

    def test_request_file_matches_date_and_research_governance(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-11-24.json"
            path.write_text(json.dumps(REQUEST))
            self.assertEqual(load_request(path), REQUEST)
            path.write_text(json.dumps({**REQUEST, "scheduled_seal_credit": True}))
            with self.assertRaisesRegex(ValueError, "GOVERNANCE_INVALID"):
                load_request(path)


if __name__ == "__main__":
    unittest.main()
