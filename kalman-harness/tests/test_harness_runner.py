"""Safety and status regression tests for the Kalman read-only harness."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("harness_runner", ROOT / "harness_runner.py")
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)
NOW = datetime(2026, 10, 16, 0, 0, tzinfo=timezone.utc)


def example_run(completed_at="2026-10-15T12:00:00Z", conclusion="success"):
    return {
        "id": 38700296186,
        "status": "completed",
        "conclusion": conclusion,
        "completed_at": completed_at,
        "url": "https://github.com/kimtk94/Codex/actions/runs/38700296186",
        "head_branch": harness.AUDIT_BRANCH,
    }


class RunnerTests(unittest.TestCase):
    def test_exact_eight_streams(self):
        self.assertEqual([x[0] for x in harness.WORKSTREAMS],
                         ["00", "01", "02", "03", "04", "05", "06", "07"])

    def test_default_no_evidence_is_not_green(self):
        r = harness.assemble(NOW, {})
        self.assertTrue(all(x["status"] != "PASS" for x in r["workstreams"]))
        self.assertEqual(r["github_checks"]["offline_quality"]["state"], "NO_RUN")
        self.assertFalse(r["production_release_authorized"])
        self.assertFalse(r["live_runtime_verified"])
        self.assertFalse(r["trading_mutations_performed"])

    def test_green_offline_does_not_unlock_live(self):
        r = harness.assemble(NOW, {"offline_quality": example_run()})
        self.assertEqual(r["github_checks"]["offline_quality"]["state"], "SUCCESS")
        self.assertEqual(r["workstreams"][6]["status"], "OFFLINE_CI_PASS_ONLY")
        self.assertFalse(r["production_release_authorized"])
        self.assertFalse(r["broker_reconciled"])
        self.assertFalse(r["live_runtime_verified"])

    def test_failed_workflow_fail_closed(self):
        r = harness.assemble(NOW, {"offline_quality": example_run(conclusion="failure")})
        self.assertEqual(r["github_checks"]["offline_quality"]["state"], "FAILURE")
        self.assertEqual(r["workstreams"][6]["status"], "EVIDENCE_REQUIRED")

    def test_stale_workflow_does_not_count_as_success(self):
        r = harness.assemble(NOW, {"offline_quality": example_run("2026-10-12T12:00:00Z")})
        self.assertEqual(r["github_checks"]["offline_quality"]["state"], "STALE")

    def test_incomplete_workflow(self):
        r = harness.assemble(NOW, {"offline_quality": {
            "status": "in_progress", "conclusion": None}})
        self.assertEqual(r["github_checks"]["offline_quality"]["state"], "IN_PROGRESS")

    def test_missing_timestamp_is_unknown(self):
        run = example_run(completed_at=None)
        self.assertEqual(harness.classify_run(run, NOW)["state"], "UNAVAILABLE")

    def test_future_timestamp_is_unknown(self):
        run = example_run(completed_at="2026-10-17T00:00:00Z")
        self.assertEqual(harness.classify_run(run, NOW)["state"], "UNAVAILABLE")

    def test_invalid_date_rejected(self):
        self.assertIsNone(harness.parse_utc("not-a-date"))
        self.assertIsNone(harness.parse_utc("2026-10-16T00:00:00"))

    def test_fixed_historical_blockers_survive_success(self):
        r = harness.assemble(NOW, {"offline_quality": example_run()})
        self.assertEqual(r["workstreams"][7]["status"], "BLOCKED_REVIEW")
        self.assertEqual(len(r["workstreams"][7]["historical_blockers"]), 4)

    def test_network_workflow_allowlist(self):
        with self.assertRaises(ValueError):
            harness.request_latest("deploy-kalman-hub-v7436.yml", "main")

    def test_network_is_get_only(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self, n=-1):
                return json.dumps({"workflow_runs": []}).encode()
        calls = []
        def fake_open(req, timeout):
            calls.append((req.get_method(), req.full_url, timeout))
            return FakeResponse()
        with patch.object(harness, "urlopen", fake_open):
            result = harness.request_latest("kalman-audit-quality.yml", harness.AUDIT_BRANCH)
        self.assertIsNone(result)
        self.assertEqual(calls[0][0], "GET")
        self.assertTrue(calls[0][1].startswith(
            "https://api.github.com/repos/kimtk94/Codex/actions/workflows/"))
        self.assertEqual(calls[0][2], 12)

    def test_markdown_label_distinguishes_live(self):
        r = harness.assemble(NOW, {"offline_quality": example_run()})
        md = harness.as_markdown(r)
        self.assertIn("LIVE verified: NO", md)
        self.assertIn("Release authorized: NO", md)
        self.assertIn("OFFLINE_CI_PASS_ONLY", md)
        self.assertNotIn("LIVE verified: YES", md)

    def test_cli_no_network_json_files(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "out"
            result = subprocess.run(
                [sys.executable, str(ROOT / "harness_runner.py"),
                 "--no-network", "--now", "2026-10-16T00:00:00Z",
                 "--output-dir", str(dest)],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((dest / "status.json").read_text())
            self.assertEqual(report["evidence_mode"], "offline_no_evidence")
            self.assertEqual(len(report["workstreams"]), 8)
            self.assertFalse(report["production_release_authorized"])
            self.assertTrue((dest / "STATUS.md").is_file())

    def test_fixture_cannot_fake_runtime_verification(self):
        with tempfile.TemporaryDirectory() as d:
            source, dest = Path(d) / "fixture.json", Path(d) / "out"
            source.write_text(json.dumps({"offline_quality": example_run()}))
            subprocess.run(
                [sys.executable, str(ROOT / "harness_runner.py"),
                 "--fixture", str(source), "--now", "2026-10-16T00:00:00Z",
                 "--output-dir", str(dest)],
                check=True, capture_output=True, timeout=15)
            report = json.loads((dest / "status.json").read_text())
            self.assertEqual(report["evidence_mode"], "local_fixture_nonlive")
            self.assertFalse(report["live_runtime_verified"])
            self.assertFalse(report["production_release_authorized"])


if __name__ == "__main__":
    unittest.main()
