"""Offline tests for CSS 9-domain / 18-crosscheck freshness policy."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from css_freshness_policy import POLICY_FILE, classify, validate_policy

NOW = "2026-11-09T00:00:00Z"


def sample(**updates):
    obs = {
        "source_probe_ok": True, "source_probe_at": "2026-11-08T23:40:00Z",
        "ingest_at": "2026-11-08T23:45:00Z",
        "sink_readback_ok": True, "sink_readback_at": "2026-11-08T23:50:00Z",
        "source_delta_count": 3, "gap_count": 0,
        "identity_parity": True, "value_parity": True,
    }
    obs.update(updates)
    return obs


class TestFreshnessPolicy(unittest.TestCase):
    def test_nine_domains_two_independent_crosschecks(self):
        self.assertTrue(validate_policy(json.loads(POLICY_FILE.read_text(encoding="utf-8"))))

    def test_missing_sink_check_fails(self):
        p = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        p["domains"][0]["checks"].pop()
        with self.assertRaisesRegex(ValueError, "DUAL_CROSSCHECK_REQUIRED"):
            validate_policy(p)

    def test_both_checks_same_axis_fails(self):
        p = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
        p["domains"][0]["checks"][1]["axis"] = "source"
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_AXES_REQUIRED"):
            validate_policy(p)

    def test_fresh_parity_is_pass(self):
        self.assertEqual(classify(sample(), now=NOW, max_probe_age_hours=6), "PASS")

    def test_zero_new_events_from_verified_source_is_normal(self):
        self.assertEqual(classify(sample(source_delta_count=0), now=NOW, max_probe_age_hours=6), "NO_NEW_DATA")

    def test_no_source_connection_is_not_zero_new_events(self):
        self.assertEqual(classify(sample(source_probe_ok=False, source_delta_count=0), now=NOW, max_probe_age_hours=6), "SOURCE_UNAVAILABLE")

    def test_stale_probe_even_if_ci_was_successful(self):
        self.assertEqual(classify(sample(source_probe_at="2026-11-07T23:40:00Z"), now=NOW, max_probe_age_hours=6), "STALE")

    def test_old_event_alone_is_not_stale(self):
        self.assertEqual(classify(sample(source_event_at="2026-10-31T00:00:00Z"), now=NOW, max_probe_age_hours=6), "PASS")

    def test_source_probe_unverified_blocks(self):
        self.assertEqual(classify(sample(source_probe_ok=None), now=NOW, max_probe_age_hours=6), "BLOCK")

    def test_missing_readback_never_pass(self):
        self.assertEqual(classify(sample(sink_readback_ok=None), now=NOW, max_probe_age_hours=6), "BLOCK")

    def test_failed_readback_is_sink_lag(self):
        self.assertEqual(classify(sample(sink_readback_ok=False), now=NOW, max_probe_age_hours=6), "SINK_LAG")

    def test_readback_before_ingest_is_sink_lag(self):
        self.assertEqual(classify(sample(sink_readback_at="2026-11-08T23:41:00Z"), now=NOW, max_probe_age_hours=6), "SINK_LAG")

    def test_missing_or_duplicate_ids_are_sink_lag(self):
        self.assertEqual(classify(sample(gap_count=1), now=NOW, max_probe_age_hours=6), "SINK_LAG")

    def test_contract_or_vat_mismatch_blocks(self):
        self.assertEqual(classify(sample(identity_parity=False), now=NOW, max_probe_age_hours=6), "BLOCK")
        self.assertEqual(classify(sample(value_parity=False), now=NOW, max_probe_age_hours=6), "BLOCK")

    def test_absent_delta_cannot_be_imputed_as_zero(self):
        self.assertEqual(classify(sample(source_delta_count=None), now=NOW, max_probe_age_hours=6), "BLOCK")

    def test_naive_or_future_timestamp_cannot_pass(self):
        self.assertEqual(classify(sample(source_probe_at="2026-11-08T23:40:00"), now=NOW, max_probe_age_hours=6), "BLOCK")
        self.assertEqual(classify(sample(sink_readback_at="2026-11-10T00:00:00Z"), now=NOW, max_probe_age_hours=6), "BLOCK")

    def test_undefined_source_cadence_cannot_pass(self):
        self.assertEqual(classify(sample(), now=NOW, max_probe_age_hours=None), "BLOCK")


if __name__ == "__main__":
    unittest.main()
