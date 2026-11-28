"""Delivery count evidence is not seal proof; exercise all failure branches."""
import unittest
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from schedule_delivery_audit import audit, latest_due_day, WORKFLOWS


def clock(day=24, hour=10, minute=30):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def fake_api(*, count=(2, 2), state=("active", "active"),
             wrong_event=False, incomplete=False, duplicate=False, running=False,
             timestamps=None):
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
             "head_branch": "main", "created_at": f"{day}T{(timestamps or (('02:40:00', '04:40:00'), ('06:25:00', '07:25:00')))[idx][i % 2]}Z",
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



class ExternalScheduleProbeTests(unittest.TestCase):
    def run_probe(self, *, when=None, token="fixture-only", env=None, fetch=None):
        from external_schedule_probe import probe
        delays = []
        report = probe(when or clock(25, 8, 20), token,
                       env=env or {}, fetch=fetch or fake_api(), sleep=delays.append)
        return report, delays

    def test_delivery_count_is_not_scientific_or_host_attestation(self):
        from external_schedule_probe import exit_code
        report, delays = self.run_probe()
        self.assertEqual(report["observed_schedule_deliveries"], 4)
        self.assertEqual(exit_code(report), 0)
        self.assertEqual(report["status"], "DELIVERY_WINDOWS_OK_NOT_SEAL_PROOF")
        self.assertEqual(report["observed_within_window_deliveries"], 4)
        self.assertTrue(report["delivery_windows_verified"])
        self.assertEqual(delays, [])
        self.assertFalse(report["host_independence_verified"])
        self.assertFalse(report["original_first_and_replay_roles_verified"])
        self.assertEqual(report["scientific_approval"], "HOLD")
        self.assertFalse(report["live_execution"])

    def test_missing_deliveries_are_not_retried_or_promoted(self):
        from external_schedule_probe import exit_code
        report, delays = self.run_probe(fetch=fake_api(count=(0, 0)))
        self.assertEqual(report["observed_schedule_deliveries"], 0)
        self.assertEqual(report["status"], "SCHEDULE_DELIVERY_HOLD")
        self.assertEqual(report["api_attempts"], 1)
        self.assertEqual(delays, [])
        self.assertEqual(exit_code(report), 2)

    def test_api_unavailable_retries_bounded_and_does_not_report_zero(self):
        from external_schedule_probe import exit_code
        def denied(path):
            raise OSError("SECRET must not appear")
        report, delays = self.run_probe(fetch=denied)
        self.assertEqual(delays, [5, 15])
        self.assertEqual(report["api_attempts"], 3)
        self.assertIsNone(report["observed_schedule_deliveries"])
        self.assertEqual(exit_code(report), 2)
        self.assertNotIn("SECRET", str(report))

    def test_transient_error_then_valid_response(self):
        calls = []
        good = fake_api()
        def transient(path):
            calls.append(path)
            if len(calls) <= 2:
                raise OSError("temporary")
            return good(path)
        report, delays = self.run_probe(fetch=transient)
        self.assertEqual(delays, [5])
        self.assertEqual(report["api_attempts"], 2)
        self.assertEqual(report["observed_schedule_deliveries"], 4)

    def test_before_cutoff_or_off_day_never_reuses_previous_day(self):
        from external_schedule_probe import exit_code
        def forbidden(path):
            self.fail("no API access expected")
        for when in (clock(25, 8, 14), clock(29, 12), clock(30, 12)):
            report, delays = self.run_probe(when=when, fetch=forbidden)
            self.assertEqual(report["status"], "NOT_DUE")
            self.assertEqual(report["target_utc_date"], when.date().isoformat())
            self.assertIsNone(report["observed_schedule_deliveries"])
            self.assertEqual(exit_code(report), 3)
            self.assertEqual(delays, [])

    def test_missing_token_or_github_host_fails_before_api(self):
        def forbidden(path):
            self.fail("no API access expected")
        for kwargs in ({"token": ""}, {"env": {"GITHUB_ACTIONS": "true"}},
                       {"env": {"GITHUB_RUN_ID": "123"}}):
            report, delays = self.run_probe(fetch=forbidden, **kwargs)
            self.assertEqual(report["status"], "API_EVIDENCE_UNAVAILABLE_HOLD")
            self.assertIsNone(report["observed_schedule_deliveries"])
            self.assertEqual(report["api_attempts"], 0)
            self.assertEqual(delays, [])

    def test_atomic_local_report_and_fail_closed_exit(self):
        from external_schedule_probe import write_report, exit_code
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        report, _ = self.run_probe(fetch=fake_api(count=(0, 0)))
        with TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "report.json"
            write_report(path, report)
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(exit_code({"status": "DELIVERY_COUNT_OK_NOT_SEAL_PROOF",
                                    "api_evidence_complete": False,
                                    "observed_schedule_deliveries": 4}), 2)

    def test_four_late_successes_are_not_on_time_delivery(self):
        from external_schedule_probe import exit_code
        report, delays = self.run_probe(
            when=clock(24, 20, 0),
            fetch=fake_api(timestamps=(("12:55:34", "15:15:53"),
                                       ("17:56:42", "18:58:47"))))
        self.assertEqual(report["delivery_count_status"], "DELIVERY_COUNT_OK_NOT_SEAL_PROOF")
        self.assertEqual(report["observed_schedule_deliveries"], 4)
        self.assertEqual(report["observed_within_window_deliveries"], 0)
        self.assertEqual(len(report["out_of_window_run_ids"]), 4)
        self.assertFalse(report["delivery_windows_verified"])
        self.assertEqual(report["status"], "SCHEDULE_DELIVERY_HOLD")
        self.assertEqual(exit_code(report), 2)
        self.assertEqual(delays, [])

    def test_two_distinct_runs_in_one_window_do_not_satisfy_other_slot(self):
        report, _ = self.run_probe(fetch=fake_api(timestamps=(
            ("02:40:00", "02:41:00"), ("06:25:00", "07:25:00"))))
        statuses = [r["status"] for r in report["delivery_window_observations"]]
        self.assertIn("MULTIPLE_RUNS_IN_WINDOW", statuses)
        self.assertIn("MISSING_WINDOW", statuses)
        self.assertEqual(report["observed_within_window_deliveries"], 4)
        self.assertFalse(report["delivery_windows_verified"])

    def test_exact_grace_boundary_and_one_second_over(self):
        report, _ = self.run_probe(fetch=fake_api(timestamps=(
            ("03:30:00", "05:30:00"), ("07:15:00", "08:15:00"))))
        self.assertTrue(report["delivery_windows_verified"])
        late, _ = self.run_probe(fetch=fake_api(timestamps=(
            ("03:30:01", "05:30:00"), ("07:15:00", "08:15:00"))))
        self.assertEqual(late["observed_within_window_deliveries"], 3)
        self.assertFalse(late["delivery_windows_verified"])

    def test_registration_before_nominal_never_gets_slot_credit(self):
        report, _ = self.run_probe(fetch=fake_api(timestamps=(
            ("02:39:59", "04:40:00"), ("06:25:00", "07:25:00"))))
        self.assertEqual(report["observed_within_window_deliveries"], 3)
        self.assertFalse(report["delivery_windows_verified"])

    def test_in_window_but_unsuccessful_runs_still_hold(self):
        from external_schedule_probe import exit_code
        report, _ = self.run_probe(fetch=fake_api(running=True))
        self.assertEqual(report["observed_within_window_deliveries"], 4)
        self.assertFalse(report["delivery_windows_verified"])
        self.assertEqual(exit_code(report), 2)



class SavedHeartbeatTests(unittest.TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from external_schedule_probe import probe, write_report
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.report = probe(clock(25, 8, 20), "fixture-only",
                            env={}, fetch=fake_api(), sleep=lambda _: None)
        write_report(self.path, self.report)

    def check(self, when=None, **kwargs):
        from external_schedule_probe import check_saved_report
        return check_saved_report(self.path, when or clock(25, 8, 30), **kwargs)

    def rewrite(self, **kwargs):
        from external_schedule_probe import write_report
        write_report(self.path, {**self.report, **kwargs})

    def test_fresh_valid_report_is_not_host_or_seal_proof(self):
        before = self.path.read_bytes()
        result, code = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(result["heartbeat_status"],
                         "FRESH_DELIVERY_WINDOWS_OK_NOT_SEAL_PROOF")
        self.assertFalse(result["host_independence_verified"])
        self.assertFalse(result["original_first_and_replay_roles_verified"])
        self.assertEqual(result["scientific_approval"], "HOLD")
        self.assertEqual(self.path.read_bytes(), before)

    def test_stale_missing_future_and_previous_day_fail(self):
        self.assertEqual(self.check(clock(25, 9, 6))[0]["reason"], "STALE_HEARTBEAT")
        self.assertEqual(self.check(clock(26, 8, 30))[0]["reason"],
                         "WRONG_REPORT_VERSION_OR_DATE")
        self.assertEqual(self.check(clock(25, 8, 19))[0]["reason"],
                         "FUTURE_REPORT_TIMESTAMP")
        self.path.unlink()
        self.assertEqual(self.check()[0]["reason"], "MISSING_HEARTBEAT")

    def test_fresh_hold_stays_hold(self):
        self.rewrite(status="SCHEDULE_DELIVERY_HOLD")
        result, code = self.check()
        self.assertEqual(code, 2)
        self.assertEqual(result["heartbeat_status"], "FRESH_DELIVERY_HOLD")

    def test_malformed_or_overclaimed_report_fails_closed(self):
        self.path.write_text("{")
        self.assertEqual(self.check()[1], 2)
        self.rewrite(scientific_approval="PASS")
        self.assertEqual(self.check()[0]["reason"], "UNVERIFIED_REPORT_BOUNDARIES")
        self.rewrite(delivery_window_observations=[])
        self.assertEqual(self.check()[0]["reason"], "INCONSISTENT_REPORT_EVIDENCE")
        self.rewrite(workflow_observations=[])
        self.assertEqual(self.check()[1], 2)

    def test_grace_and_maximum_age_boundary(self):
        self.assertEqual(self.check(clock(25, 8, 14))[1], 3)
        self.assertEqual(self.check(clock(25, 9, 5))[1], 0)
        self.assertEqual(self.check(max_age_minutes=0)[1], 2)
        self.assertEqual(self.check(clock(29, 12, 0))[1], 3)




if __name__ == "__main__":
    unittest.main()
