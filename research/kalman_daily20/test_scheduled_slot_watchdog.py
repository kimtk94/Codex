"""No-network falsification tests for both scheduled-slot heartbeat check."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import unittest

from scheduled_slot_watchdog import (
    FIRST, SECOND, VERSION, evaluate, job_evidence,
    one_record, READY_RE, POST_RE,
)

UTC_DAY = date(2026, 11, 24)
NOW = datetime(2026, 11, 24, 6, 30, tzinfo=timezone.utc)
SESSION = "2026-11-23"
SHA = "a" * 64
MODEL = "b" * 40


def witness(slot, *, first_id=810, second_id=811, due=True):
    first = slot == FIRST
    rid = first_id if first else second_id
    start = "2026-11-24T02:41:00Z" if first else "2026-11-24T04:41:00Z"
    count = (60 if due else 0) if first else 0
    mode = ("FIRST_GENUINE_SEAL_EXPECTED" if first and due else
            "SAME_SESSION_REPLAY_EXPECTED")
    original = first_id if due else 780
    return {
        "run_id": rid,
        "run_url": f"https://github.com/kimtk94/Codex/actions/runs/{rid}",
        "created_at": start,
        "status": "completed",
        "conclusion": "success",
        "event": "schedule",
        "head_branch": "main",
        "head_sha": MODEL,
        "slot": slot, "session": SESSION, "mode": mode,
        "missing_successful_jobs": [],
        "post": {
            "session": SESSION, "mode": mode,
            "status": "FIRST_SEAL_26_PRICE_420_FEATURE_40_MODEL_60_EVENT_ATTESTED_HOLD"
            if count == 60 else "SAME_SESSION_REPLAY_INPUTS_UNCHANGED_SOURCE_HOLD",
            "new": str(count), "changed": "False",
        },
        "first_seal_readback": {
            "session": SESSION, "status":
            "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD",
            "deep": 1, "current": True,
            "original_run": original,
            "snapshot_sha256": SHA,
        },
        "remote_drive_readback": True,
    }


def judge(*runs, due=True, now=NOW, session=SESSION):
    return evaluate(UTC_DAY, expected_session=session,
                    new_session_due=due, runs=list(runs), now=now)


class ScheduledSlotWatchdogTests(unittest.TestCase):
    def test_both_missing_is_explicit_failure(self):
        r = judge()
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("BOTH_SCHEDULED_SLOTS_MISSING", r["problem_codes"])
        self.assertIsNone(r["first_run_id"])
        self.assertIsNone(r["second_run_id"])
        self.assertEqual(r["scientific_approval"], "HOLD")

    def test_first_missing_does_not_accept_late_second_green(self):
        r = judge(witness(SECOND))
        self.assertIn("MISSING_FIRST_SLOT", r["problem_codes"])
        self.assertNotIn("MISSING_SECOND_SLOT", r["problem_codes"])
        self.assertEqual(r["status"], "FAIL")

    def test_second_missing_not_a_pass_even_if_first_remote_saved(self):
        r = judge(witness(FIRST))
        self.assertIn("MISSING_SECOND_SLOT", r["problem_codes"])
        self.assertEqual(r["status"], "FAIL")

    def test_two_independent_runs_attested_still_research_hold(self):
        r = judge(witness(FIRST), witness(SECOND))
        self.assertEqual(r["status"], "PASS")
        self.assertFalse(r["problem_codes"])
        self.assertEqual((r["first_run_id"], r["second_run_id"]), (810, 811))
        self.assertTrue(r["new_xnys_session_due"])
        self.assertEqual(r["expected_first_new_signals"], 60)
        self.assertEqual(r["expected_second_new_signals"], 0)
        self.assertEqual(r["scientific_approval"], "HOLD")
        self.assertFalse(r["strategy_promoted"])

    def test_two_successful_push_runs_never_replace_schedules(self):
        a, b = witness(FIRST), witness(SECOND)
        a["event"] = "push"
        b["event"] = "workflow_dispatch"
        r = judge(a, b)
        self.assertIn("BOTH_SCHEDULED_SLOTS_MISSING", r["problem_codes"])
        self.assertEqual(r["status"], "FAIL")

    def test_second_must_not_append_any_new_signal(self):
        b = witness(SECOND)
        b["post"]["new"] = "60"
        r = judge(witness(FIRST), b)
        self.assertIn("SECOND_POSTFLIGHT_MISSING_OR_WRONG_COUNT",
                      r["problem_codes"])

    def test_first_must_capture_all_sixty(self):
        a = witness(FIRST)
        a["post"]["new"] = "40"
        self.assertIn("FIRST_POSTFLIGHT_MISSING_OR_WRONG_COUNT",
                      judge(a, witness(SECOND))["problem_codes"])

    def test_replay_snapshot_sha_change_detected(self):
        b = witness(SECOND)
        b["first_seal_readback"]["snapshot_sha256"] = "b" * 64
        r = judge(witness(FIRST), b)
        self.assertIn("INDEPENDENT_REPLAY_DID_NOT_PRESERVE_ORIGINAL_SEAL",
                      r["problem_codes"])

    def test_replay_original_run_drift_detected(self):
        b = witness(SECOND)
        b["first_seal_readback"]["original_run"] = 700
        r = judge(witness(FIRST), b)
        self.assertIn("INDEPENDENT_REPLAY_DID_NOT_PRESERVE_ORIGINAL_SEAL",
                      r["problem_codes"])
        self.assertIn("SECOND_REPLAY_NOT_LINKED_TO_FIRST_RUN", r["problem_codes"])

    def test_first_seal_origin_must_match_first_run(self):
        a = witness(FIRST)
        a["first_seal_readback"]["original_run"] = 700
        self.assertIn("FIRST_ORIGINAL_RUN_PROVENANCE_NOT_FIRST_JOB",
                      judge(a, witness(SECOND))["problem_codes"])

    def test_first_and_replay_same_run_id_rejected(self):
        b = witness(SECOND)
        b["run_id"] = 810
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_INVALID_GITHUB_RUN"):
            judge(witness(FIRST), b)

    def test_two_schedules_must_have_identical_code_commit(self):
        b = witness(SECOND)
        b["head_sha"] = "c" * 40
        self.assertIn("CODE_SHA_CHANGED_BETWEEN_REPLAYS",
                      judge(witness(FIRST), b)["problem_codes"])

    def test_failed_first_job_cannot_look_green(self):
        a = witness(FIRST)
        a["status"] = "completed"
        a["conclusion"] = "failure"
        a["missing_successful_jobs"] = ["persist-google-drive"]
        self.assertIn("FIRST_WORKFLOW_OR_JOB_FAILED",
                      judge(a, witness(SECOND))["problem_codes"])

    def test_running_second_not_counted_as_completed(self):
        b = witness(SECOND)
        b["status"] = "in_progress"
        b["conclusion"] = None
        self.assertIn("SECOND_WORKFLOW_OR_JOB_FAILED",
                      judge(witness(FIRST), b)["problem_codes"])

    def test_missing_remote_drive_readback_fails(self):
        b = witness(SECOND)
        b["remote_drive_readback"] = False
        self.assertIn("SECOND_DRIVE_READBACK_NOT_VERIFIED",
                      judge(witness(FIRST), b)["problem_codes"])

    def test_missing_original_input_anchor_fails_even_if_jobs_green(self):
        b = witness(SECOND)
        b["first_seal_readback"] = None
        failures = judge(witness(FIRST), b)["problem_codes"]
        self.assertIn("SECOND_ORIGINAL_FIRST_SEAL_REMOTE_PROOF_MISSING", failures)
        self.assertIn("INDEPENDENT_REPLAY_DID_NOT_PRESERVE_ORIGINAL_SEAL", failures)

    def test_mismatched_market_session_fails(self):
        b = witness(SECOND)
        b["session"] = "2026-11-20"
        self.assertIn("SECOND_WRONG_SESSION_OR_ROLE",
                      judge(witness(FIRST), b)["problem_codes"])

    def test_ambiguous_double_scheduled_first_runs_fail(self):
        extra = witness(FIRST, first_id=812)
        r = judge(witness(FIRST), extra, witness(SECOND))
        self.assertIn("AMBIGUOUS_FIRST_SLOT", r["problem_codes"])
        self.assertEqual(r["status"], "FAIL")

    def test_scheduled_but_missing_role_evidence_is_not_ignored(self):
        a = witness(FIRST)
        a["slot"] = None
        r = judge(a, witness(SECOND))
        self.assertIn("SCHEDULED_RUN_WITHOUT_ROLE_EVIDENCE", r["problem_codes"])
        self.assertIn("MISSING_FIRST_SLOT", r["problem_codes"])

    def test_market_holiday_does_not_fake_new_frozen_events(self):
        a, b = witness(FIRST, due=False), witness(SECOND, due=False)
        a["session"] = b["session"] = "2026-11-25"
        a["post"]["session"] = b["post"]["session"] = "2026-11-25"
        a["first_seal_readback"]["session"] = "2026-11-25"
        b["first_seal_readback"]["session"] = "2026-11-25"
        # 2026 Nov 26 Thanksgiving, monitoring date Nov 27.
        later = datetime(2026, 11, 27, 6, 30, tzinfo=timezone.utc)
        a["created_at"] = "2026-11-27T02:41:00Z"
        b["created_at"] = "2026-11-27T04:41:00Z"
        r = evaluate(date(2026, 11, 27), expected_session="2026-11-25",
                     new_session_due=False, runs=[a, b], now=later)
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["expected_first_new_signals"], 0)
        self.assertEqual(r["expected_second_new_signals"], 0)

    def test_holiday_first_fake_new_signal_is_rejected(self):
        a, b = witness(FIRST, due=False), witness(SECOND, due=False)
        a["mode"] = "FIRST_GENUINE_SEAL_EXPECTED"
        a["post"]["mode"] = "FIRST_GENUINE_SEAL_EXPECTED"
        self.assertIn("FIRST_WRONG_SESSION_OR_ROLE",
                      judge(a, b, due=False)["problem_codes"])

    def test_audit_cannot_conclude_before_0615_utc(self):
        with self.assertRaisesRegex(ValueError, "AUDIT_BEFORE_TWO_SLOTS_DUE"):
            judge(witness(FIRST), witness(SECOND),
                  now=datetime(2026, 11, 24, 4, 40, tzinfo=timezone.utc))

    def test_previous_days_schedule_cannot_reuse_success(self):
        old = witness(FIRST)
        old["created_at"] = "2026-11-23T02:41:00Z"
        with self.assertRaisesRegex(ValueError, "RUN_FROM_ANOTHER_DATE"):
            judge(old, witness(SECOND))

    def test_wrong_post_mode_does_not_pass(self):
        b = witness(SECOND)
        b["post"]["mode"] = "FIRST_GENUINE_SEAL_EXPECTED"
        self.assertIn("SECOND_POSTFLIGHT_MISSING_OR_WRONG_COUNT",
                      judge(witness(FIRST), b)["problem_codes"])

    def test_real_emitted_log_lines_are_parsed_not_shell_source(self):
        signal = ("2026-11-24T03:04:11Z DAILY20_TWO_PASS_PHASE_READY "
                  "2026-11-23 FIRST_GENUINE_SEAL_EXPECTED slot 40 2 * * 2-6")
        post = ("2026-11-24T03:07:08Z DAILY20_TWO_PASS_INTEGRITY_HOLD "
                "2026-11-23 mode FIRST_GENUINE_SEAL_EXPECTED "
                "status FIRST_SEAL_26_PRICE_420_FEATURE_40_MODEL_60_EVENT_ATTESTED_HOLD "
                "changed False new 60")
        self.assertEqual(one_record(signal, READY_RE)["slot"], FIRST)
        self.assertEqual(one_record(post, POST_RE)["new"], "60")
        self.assertIsNone(one_record(signal + "\n" + signal, READY_RE))
        self.assertIsNone(one_record('print("DAILY20_TWO_PASS_PHASE_READY")',
                                     READY_RE))

    def test_real_publisher_readback_and_first_seal_log_are_both_required(self):
        run = {"id": 810, "event": "schedule", "head_branch": "main",
               "head_sha": MODEL, "created_at": "2026-11-24T02:41:00Z",
               "status": "completed", "conclusion": "success"}
        research = (
            "2026Z DAILY20_TWO_PASS_PHASE_READY 2026-11-23 "
            "FIRST_GENUINE_SEAL_EXPECTED slot 40 2 * * 2-6\n"
            "2026Z DAILY20_TWO_PASS_INTEGRITY_HOLD 2026-11-23 "
            "mode FIRST_GENUINE_SEAL_EXPECTED status "
            "FIRST_SEAL_26_PRICE_420_FEATURE_40_MODEL_60_EVENT_ATTESTED_HOLD "
            "changed False new 60"
        )
        publish = (
            '2026Z ***"DAILY20_DRIVE_READBACK": ***'
            '"version": "daily20-drive-readback-v1", '
            '"status": "READBACK_VERIFIED", "session": "2026-11-23"***'
            "\n2026Z DAILY20_FIRST_SEAL_CHECK_V1 session=2026-11-23 "
            "status=NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD "
            "deep=1 current=YES original_run=810 snapshot_sha=" + SHA
        )
        jobs = [
            {"name": name, "conclusion": "success"}
            for name in ("contracts", "restore-drive-cache",
                         "daily-research", "persist-google-drive")
        ]
        evidence = job_evidence(run, jobs, research, publish)
        self.assertEqual(evidence["slot"], FIRST)
        self.assertEqual(evidence["post"]["new"], "60")
        self.assertTrue(evidence["remote_drive_readback"])
        self.assertEqual(evidence["first_seal_readback"]["original_run"], 810)
        self.assertEqual(judge(evidence, witness(SECOND))["status"], "PASS")
        modified = publish.replace('"session": "2026-11-23"',
                                   '"session": "2026-11-20"')
        self.assertFalse(job_evidence(run, jobs, research, modified)[
            "remote_drive_readback"])

    def test_dont_accept_fake_legacy_first_seal_log(self):
        run = {"id": 810, "event": "schedule", "head_branch": "main",
               "head_sha": MODEL, "created_at": "2026-11-24T02:41:00Z",
               "status": "completed", "conclusion": "success"}
        research = (
            "DAILY20_TWO_PASS_PHASE_READY 2026-11-20 "
            "LEGACY_REPLAY_NO_20261120_ORIGINAL_FEATURES_HOLD slot NON_SCHEDULED\n"
        )
        publisher = ('***"DAILY20_DRIVE_READBACK": '
                     '"status": "READBACK_VERIFIED", "session": "2026-11-20"***')
        result = job_evidence(run, [
            {"name": name, "conclusion": "success"}
            for name in ("contracts", "restore-drive-cache",
                         "daily-research", "persist-google-drive")
        ], research, publisher)
        self.assertIsNone(result["slot"])
        self.assertIsNone(result["first_seal_readback"])
        self.assertFalse(result["remote_drive_readback"] is True and
                         result["session"] == SESSION)


if __name__ == "__main__":
    unittest.main()
