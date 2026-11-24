"""Readiness monitor tests: green pipeline never equals approved trading."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from ops_readiness import (SafeGitHubLogRedirect, make_scorecard, parse_diagnostics,
                           parse_first_seal_check, safe_job_log)

NOW = datetime(2026, 11, 22, 10, tzinfo=timezone.utc)
RUN = {
    "id": 45003032896, "head_branch": "main", "event": "push",
    "conclusion": "success", "created_at": "2026-11-22T08:29:16Z",
    "html_url": "https://github.com/kimtk94/Codex/actions/runs/45003032896",
}
JOBS = [{"name": n, "conclusion": "success"} for n in (
    "contracts", "restore-drive-cache", "daily-research", "persist-google-drive")]
LOG = "\n".join([
    '2026-11-22T08:31:00Z {"DAILY20_REFRESH": {"mode": "INCREMENTAL", "asset_count": 26}}',
    '2026-11-22T08:31:04Z {"DAILY20_SOURCE_FINALITY": {"session": "2026-11-20", "verified": 0, "required": 26, "status": "SOURCE_FINALITY_HOLD"}}',
    '2026-11-22T08:31:30Z DAILY20_OOS 1499 trades 20 research-only scores',
    '2026-11-22T08:31:31Z {"DAILY20_PORTFOLIO": "COMPLETE", "scenarios": 16}',
    '2026-11-22T08:31:42Z {"DAILY20_FORWARD_SHADOW": {"signals": 20, "frozen_replay_drift": 20, "settled": 0}}',
    '2026-11-22T08:31:49Z {"DAILY20_STABILITY": {"status": "REPLAY_DRIFT_RESEARCH_HOLD", "hold": true, "incidents": 4}}',
])
PUBLISH = '2026-11-22T08:32:21Z ***"DAILY20_DRIVE_READBACK": ***"status": "READBACK_VERIFIED", "session": "2026-11-20"***'
PUBLISH += ("\n2026Z DAILY20_FIRST_SEAL_CHECK_V1 "
            "session=2026-11-20 status=AWAITING_GENUINE_NEW_SESSION "
            "deep=0 current=NO original_run=NONE snapshot_sha=NONE")
FUTURE_NOW = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)
FUTURE_RUN = dict(RUN, id=45030000010, created_at="2026-11-24T03:10:00Z")
FUTURE_LOG = (LOG.replace("2026-11-20", "2026-11-23")
              .replace('"frozen_replay_drift": 20, "settled": 0',
                       '"frozen_replay_drift": 0, "new_signals": 20, "settled": 0'))
FUTURE_PUBLISH = (PUBLISH.splitlines()[0].replace("2026-11-20", "2026-11-23")
    + "\n2026Z DAILY20_FIRST_SEAL_CHECK_V1 session=2026-11-23 "
      "status=NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD "
      "deep=1 current=YES original_run=45030000010 snapshot_sha=" + "a" * 64)



class ReadinessTest(unittest.TestCase):
    def test_legacy_actual_readback_awating_future_is_not_false_failure(self):
        r = make_scorecard(RUN, JOBS, LOG, PUBLISH, now=NOW)
        self.assertEqual(r["operational_status"], "PASS")
        self.assertEqual(r["first_seal_deep_verified"], 0)
        self.assertEqual(r["independent_same_session_replay_status"],
                         "LEGACY_AWAITING_GENUINE_NEW_SESSION")

    def test_new_original_26_420_40_60_seal_attested_but_replay_pending(self):
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG, FUTURE_PUBLISH,
                           now=FUTURE_NOW)
        self.assertEqual(r["operational_status"], "PASS")
        self.assertEqual(r["research_status"], "HOLD")
        self.assertEqual(r["first_seal_original_run_id"], FUTURE_RUN["id"])
        self.assertEqual(r["first_seal_original_snapshot_sha256"], "a" * 64)
        self.assertEqual(r["independent_same_session_replay_status"],
                         "FIRST_SEAL_REMOTE_READBACK_VERIFIED")
        self.assertIn("WAITING_INDEPENDENT_SAME_SESSION_REPLAY",
                      r["research_hold_reasons"])

    def test_automatic_two_hours_later_replay_uses_earlier_orig_event_run(self):
        replay_run = dict(FUTURE_RUN, id=45030000100,
                          created_at="2026-11-24T05:15:00Z")
        replay_log = FUTURE_LOG.replace('"new_signals": 20',
                                        '"new_signals": 0')
        r = make_scorecard(replay_run, JOBS, replay_log, FUTURE_PUBLISH,
                           now=datetime(2026, 11, 24, 6, tzinfo=timezone.utc))
        self.assertEqual(r["operational_status"], "PASS")
        self.assertEqual(r["independent_same_session_replay_status"],
                         "SAME_SESSION_ORIGINAL_INPUT_REPLAY_VERIFIED")
        self.assertNotIn("WAITING_INDEPENDENT_SAME_SESSION_REPLAY",
                         r["research_hold_reasons"])
        self.assertEqual(r["research_status"], "HOLD")  # Independent close 0/26.

    def test_cumulative_journal_is_not_current_score_count(self):
        log = FUTURE_LOG.replace('"signals": 20', '"signals": 40')
        r = make_scorecard(FUTURE_RUN, JOBS, log, FUTURE_PUBLISH, now=FUTURE_NOW)
        self.assertEqual(r["operational_status"], "PASS")
        self.assertEqual(r["research_scores"], 20)
        self.assertEqual(r["forward_journal_signals"], 40)
        self.assertEqual(r["research_status"], "HOLD")

    def test_wrong_missing_or_duplicate_daily_score_evidence_fails(self):
        for log in (LOG.replace("20 research-only scores", "19 research-only scores"),
                    LOG.replace("DAILY20_OOS", "MISSING_OOS"),
                    LOG + "\n2026Z DAILY20_OOS 1499 trades 20 research-only scores"):
            r = make_scorecard(RUN, JOBS, log, PUBLISH, now=NOW)
            self.assertIn("RESEARCH_SCORE_COUNT_NOT_20", r["operational_failures"])

    def test_invalid_journal_count_still_fails_closed(self):
        for value in (0, 19, 21, 41):
            log = LOG.replace('"signals": 20', f'"signals": {value}')
            r = make_scorecard(RUN, JOBS, log, PUBLISH, now=NOW)
            self.assertIn("FORWARD_JOURNAL_COUNT_INVALID", r["operational_failures"])

    def test_new_closed_day_missing_first_seal_fails_ops(self):
        broken = FUTURE_PUBLISH.replace(
            "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD",
            "AWAITING_GENUINE_NEW_SESSION"
        ).replace("deep=1 current=YES original_run=45030000010 snapshot_sha=" + "a" * 64,
                  "deep=0 current=NO original_run=NONE snapshot_sha=NONE")
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG, broken, now=FUTURE_NOW)
        self.assertIn("NEW_SESSION_FIRST_SEAL_UNVERIFIED", r["operational_failures"])
        self.assertEqual(r["research_status"], "HOLD")

    def test_new_closed_day_missing_proof_line_fails_ops(self):
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG,
                           FUTURE_PUBLISH.splitlines()[0], now=FUTURE_NOW)
        self.assertIn("FIRST_SEAL_READBACK_ATTESTATION_MISSING",
                      r["operational_failures"])

    def test_new_day_seal_source_run_cannot_be_later_than_current(self):
        broken = FUTURE_PUBLISH.replace("original_run=45030000010",
                                        "original_run=45030000555")
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG, broken, now=FUTURE_NOW)
        self.assertIn("FIRST_SEAL_ORIGINAL_RUN_ID_MISMATCH",
                      r["operational_failures"])

    def test_replay_cannot_claim_its_own_id_as_original(self):
        replay_run = dict(FUTURE_RUN, id=45030000100)
        replay_log = FUTURE_LOG.replace('"new_signals": 20',
                                        '"new_signals": 0')
        broken = FUTURE_PUBLISH.replace("original_run=45030000010",
                                        "original_run=45030000100")
        r = make_scorecard(replay_run, JOBS, replay_log, broken, now=FUTURE_NOW)
        self.assertIn("SAME_SESSION_REPLAY_ORIGINAL_RUN_NOT_EARLIER",
                      r["operational_failures"])

    def test_new_day_different_remote_session_fails(self):
        broken = FUTURE_PUBLISH.replace(
            "DAILY20_FIRST_SEAL_CHECK_V1 session=2026-11-23",
            "DAILY20_FIRST_SEAL_CHECK_V1 session=2026-11-20")
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG, broken, now=FUTURE_NOW)
        self.assertIn("NEW_SESSION_FIRST_SEAL_UNVERIFIED", r["operational_failures"])

    def test_invalid_sha_and_duplicated_proof_are_rejected(self):
        broken = FUTURE_PUBLISH.replace("snapshot_sha=" + "a" * 64,
                                        "snapshot_sha=" + "wrong")
        r = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG, broken, now=FUTURE_NOW)
        self.assertIn("FIRST_SEAL_READBACK_ATTESTATION_MISSING",
                      r["operational_failures"])
        r2 = make_scorecard(FUTURE_RUN, JOBS, FUTURE_LOG,
                            FUTURE_PUBLISH + "\n" + FUTURE_PUBLISH.splitlines()[-1],
                            now=FUTURE_NOW)
        self.assertIn("FIRST_SEAL_READBACK_ATTESTATION_MISSING",
                      r2["operational_failures"])

    def test_legacy_fake_future_seal_rejected(self):
        broken = (PUBLISH.splitlines()[0] + "\n" +
                  FUTURE_PUBLISH.splitlines()[1])
        r = make_scorecard(RUN, JOBS, LOG, broken, now=NOW)
        self.assertIn("LEGACY_FAKE_PROSPECTIVE_EVIDENCE", r["operational_failures"])

    def test_unknown_partial_admission_does_not_count_as_first_seal(self):
        changed = FUTURE_LOG.replace('"new_signals": 20',
                                     '"new_signals": 5')
        r = make_scorecard(FUTURE_RUN, JOBS, changed, FUTURE_PUBLISH,
                           now=FUTURE_NOW)
        self.assertIn("NEW_SESSION_PARTIAL_OR_UNKNOWN_ADMISSION",
                      r["operational_failures"])

    def test_healthy_ops_not_research_ready(self):
        c = make_scorecard(RUN, JOBS, LOG, PUBLISH, now=NOW)
        self.assertEqual(c["operational_status"], "PASS")
        self.assertEqual(c["research_status"], "HOLD")
        self.assertEqual((c["source_certified"], c["source_required"]), (0, 26))
        self.assertEqual(c["forward_replay_drift"], 20)
        self.assertFalse(c["strategy_promoted"])

    def test_missing_drive_readback_fails_ops(self):
        c = make_scorecard(RUN, JOBS, LOG, "", now=NOW)
        self.assertIn("DRIVE_READBACK_MISSING", c["operational_failures"])

    def test_stale_run_fails_ops(self):
        stale = dict(RUN, created_at="2026-11-01T00:00:00Z")
        c = make_scorecard(stale, JOBS, LOG, PUBLISH, now=NOW)
        self.assertIn("RUN_STALE_OR_CLOCK_INVALID", c["operational_failures"])

    def test_missing_source_diagnostic_not_silently_ready(self):
        c = make_scorecard(RUN, JOBS, LOG.replace('"DAILY20_SOURCE_FINALITY"', '"MISSING_SOURCE"'), PUBLISH, now=NOW)
        self.assertEqual(c["operational_status"], "FAIL")
        self.assertEqual(c["research_status"], "HOLD")

    def test_failed_job_fails_ops(self):
        jobs = [dict(j) for j in JOBS]
        jobs[-1]["conclusion"] = "failure"
        c = make_scorecard(RUN, jobs, LOG, PUBLISH, now=NOW)
        self.assertIn("JOB_NOT_SUCCESS:persist-google-drive", c["operational_failures"])

    def test_invalid_json_does_not_enter_diagnostics(self):
        self.assertEqual(parse_diagnostics('2026Z {"DAILY20_SOURCE_FINALITY": INVALID}'), {})


    def test_github_signed_redirect_does_not_forward_bearer(self):
        handler = SafeGitHubLogRedirect()
        req = Request("https://api.github.com/repos/kimtk94/Codex/actions/jobs/123/logs",
                      headers={"Authorization": "Bearer SECRET"})
        redirected = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://pipelines.actions.githubusercontent.com/redirected/download?sig=hidden")
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertEqual(redirected.host, "pipelines.actions.githubusercontent.com")

    def test_redirect_rejects_external_non_https_or_untrusted_domain(self):
        handler = SafeGitHubLogRedirect()
        req = Request("https://api.github.com/repos/kimtk94/Codex/actions/jobs/123/logs",
                      headers={"Authorization": "Bearer SECRET"})
        for url in (
            "http://pipelines.actions.githubusercontent.com/unsafe",
            "https://attacker.example/redirect",
            "https://bad-actions.githubusercontent.com.evil.org/download",
        ):
            with self.assertRaisesRegex(ValueError, "UNTRUSTED_GITHUB_LOG_REDIRECT"):
                handler.redirect_request(req, None, 302, "Found", {}, url)

    def test_github_blob_host_allowed_without_auth(self):
        handler = SafeGitHubLogRedirect()
        req = Request("https://api.github.com/repos/kimtk94/Codex/actions/jobs/123/logs",
                      headers={"Authorization": "Bearer SECRET"})
        redirected = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://productionresultssa12.blob.core.windows.net/signed?sig=test")
        self.assertIsNone(redirected.get_header("Authorization"))

    def test_download_http_401_returns_hard_hold_without_exception_payload(self):
        url = "https://api.github.com/repos/kimtk94/Codex/actions/jobs/123/logs"
        failure = HTTPError(url, 401, "Server failed to authenticate", None, None)
        with patch("ops_readiness.api", side_effect=failure):
            log, code = safe_job_log("https://api.github.com/repos/kimtk94/Codex",
                                      123, "SECRET", "daily-research")
        self.assertEqual(log, "")
        self.assertEqual(code, "GITHUB_LOG_DOWNLOAD_FAILED:daily-research")
        self.assertNotIn("SECRET", code)

    def test_missing_job_id_is_explicit_not_silent(self):
        log, code = safe_job_log("https://api.github.com/repos/kimtk94/Codex",
                                  None, "SECRET", "persist-google-drive")
        self.assertEqual(log, "")
        self.assertEqual(code, "JOB_ID_NOT_FOUND:persist-google-drive")


if __name__ == "__main__":
    unittest.main()
