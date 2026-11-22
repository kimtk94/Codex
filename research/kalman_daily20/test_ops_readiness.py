"""Readiness monitor tests: green pipeline never equals approved trading."""
import unittest
from datetime import datetime, timezone
from ops_readiness import make_scorecard, parse_diagnostics

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
    '2026-11-22T08:31:31Z {"DAILY20_PORTFOLIO": "COMPLETE", "scenarios": 16}',
    '2026-11-22T08:31:42Z {"DAILY20_FORWARD_SHADOW": {"signals": 20, "frozen_replay_drift": 20, "settled": 0}}',
    '2026-11-22T08:31:49Z {"DAILY20_STABILITY": {"status": "REPLAY_DRIFT_RESEARCH_HOLD", "hold": true, "incidents": 4}}',
])
PUBLISH = '2026-11-22T08:32:21Z ***"DAILY20_DRIVE_READBACK": ***"status": "READBACK_VERIFIED", "session": "2026-11-20"***'


class ReadinessTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
