"""Offline synthetic regression for Novogene CSS P0 readiness evaluator."""
import datetime as dt
import unittest
from css_release_readiness import MAX_AGE_DAYS, evaluate, synthetic_example

NOW = dt.datetime(2026, 10, 17, 9, 0, tzinfo=dt.timezone.utc)

def all_pass():
    manifest = synthetic_example(now=NOW)
    for item in manifest["checks"].values():
        item["status"] = "PASS"
    return manifest

class ReadinessTests(unittest.TestCase):
    def test_synthetic_blocked(self):
        report = evaluate(synthetic_example(now=NOW), now=NOW)
        self.assertEqual(report["evaluation"], "BLOCKED")
        self.assertFalse(report["production_deploy_authorized"])
        self.assertEqual({x["gate"] for x in report["blocking_checks"]}, {
            "runtime_health", "full_engine_sink_isolation",
            "isolated_full_css_main", "manual_deployment_approval"})

    def test_all_pass_still_not_authorized(self):
        result = evaluate(all_pass(), now=NOW)
        self.assertEqual(result["evaluation"], "READY_FOR_HUMAN_REVIEW")
        self.assertTrue(result["ready_for_human_review"])
        self.assertFalse(result["production_deploy_authorized"])

    def test_missing_required_gate_fails_closed(self):
        for gate in MAX_AGE_DAYS:
            with self.subTest(gate=gate):
                data = all_pass()
                del data["checks"][gate]
                self.assertEqual(evaluate(data, now=NOW)["checks"][gate], "UNKNOWN")

    def test_nonpassing_statuses_fails_closed(self):
        for status in ("FAIL", "BLOCKED", "PARTIAL", "NOT_RUN",
                       "NOT_REQUESTED", "UNKNOWN", "OK", None, True):
            with self.subTest(status=status):
                data = all_pass()
                data["checks"]["full_engine_sink_isolation"]["status"] = status
                self.assertEqual(evaluate(data, now=NOW)["evaluation"], "BLOCKED")

    def test_invalid_future_and_old_timestamps(self):
        for value, expected in (
            (None, "MISSING_TIMESTAMP"),
            ("n/a", "MISSING_TIMESTAMP"),
            ("2026-10-17T09:00:00", "MISSING_TIMESTAMP"),
            ("2026-10-17T09:06:00Z", "FUTURE_TIMESTAMP"),
            ("2026-10-14T09:00:00Z", "STALE_EVIDENCE")):
            with self.subTest(value=value):
                data = all_pass()
                data["checks"]["source_fingerprint"]["observed_at_utc"] = value
                self.assertEqual(evaluate(data, now=NOW)["checks"]["source_fingerprint"], expected)

    def test_runtime_freshness_boundary(self):
        data = all_pass()
        data["checks"]["runtime_health"]["observed_at_utc"] = "2026-10-16T09:00:00Z"
        self.assertEqual(evaluate(data, now=NOW)["evaluation"], "READY_FOR_HUMAN_REVIEW")

    def test_reject_live_and_invalid_manifests(self):
        for data in (None, [], {}, {"schema_version": 2, "environment": "staging", "checks": {}},
                     {"schema_version": 1, "environment": "production", "checks": {}},
                     {"schema_version": 1, "environment": "staging", "checks": []}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    evaluate(data, now=NOW)

    def test_sensitive_input_not_returned(self):
        data = all_pass()
        data["email"] = "sensitive@example.invalid"
        data["checks"]["source_fingerprint"]["notes"] = "secret"
        result = evaluate(data, now=NOW)
        self.assertNotIn("sensitive@example.invalid", str(result))
        self.assertNotIn("secret", str(result))

    def test_utc_offset_aware_current_time(self):
        now = NOW.astimezone(dt.timezone(dt.timedelta(hours=9)))
        self.assertEqual(evaluate(all_pass(), now=now)["evaluation"], "READY_FOR_HUMAN_REVIEW")

    def test_naive_current_time_denied(self):
        with self.assertRaises(ValueError):
            evaluate(all_pass(), now=dt.datetime(2026, 10, 17, 9))

if __name__ == "__main__":
    unittest.main()
