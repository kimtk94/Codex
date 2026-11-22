"""Offline contracts for read-only legacy Bull/Bear/stability reconciliation."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from daily20 import load_spec
from replay_drift_reconciliation import reconcile, csv_bytes

SPEC = load_spec()
SESSION = "2026-11-20"
IMPORTANT = {"SPY": 1.8623, "AMZN": 1.6174, "GOOGL": 1.2434, "NVDA": 1.1668}


def fixture(*, legacy=True, no_drift=False):
    symbols = list(SPEC["core"])
    bull_diffs, incidents, bear_diffs = [], [], []
    for n, symbol in enumerate(symbols):
        delta_pp = 0 if no_drift else IMPORTANT.get(symbol, 0.05)
        frozen, current = 0.4, 0.4 + delta_pp / 100
        if not no_drift:
            bull_diffs.append({
                "symbol": symbol,
                "frozen_probability": frozen, "recomputed_probability": current,
                "frozen_candidate": False, "recomputed_candidate": False,
                "frozen_shadow_only": symbol in SPEC["high_risk_shadow_only"],
                "recomputed_shadow_only": symbol in SPEC["high_risk_shadow_only"],
                "frozen_event_hash": sha256(("BULL-" + symbol).encode()).hexdigest(),
                "classification": "REPLAY_DRIFT_NO_FROZEN_EVENT_MODIFIED",
            })
            if symbol in IMPORTANT:
                incidents.append({
                    "symbol": symbol, "family": "BULL_LOGISTIC",
                    "candidate_flip": False, "probability_delta_pp": delta_pp,
                    "legacy_event_only_no_original_feature_snapshot": True,
                    "research_hold": True,
                })
        for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
            if not no_drift and n < 16:
                bear_diffs.append({
                    "symbol": symbol, "family": family,
                    "frozen_probability": 0.35 if family == "BEAR_LOGISTIC" else None,
                    "recomputed_probability": 0.35 if family == "BEAR_LOGISTIC" else None,
                    "frozen_candidate": False, "recomputed_candidate": False,
                    "changed_fields": ["rsi14"],
                    "frozen_event_hash": sha256((family + symbol).encode()).hexdigest(),
                })
    return {
        "bull": {
            "version": "daily20-forward-shadow-v1",
            "last_completed_session": SESSION,
            "research_only": True, "approved_live": False,
            "new_signal_events": 0 if legacy else 20,
            "signal_events": 20,
            "frozen_replay_drift_count": len(bull_diffs),
            "frozen_replay_differences": bull_diffs,
        },
        "bear": {
            "version": "daily20-bear-forward-v1",
            "last_completed_session": SESSION,
            "research_only": True, "approved_live": False,
            "no_broker_order": True,
            "new_signal_events": 0 if legacy else 40,
            "signal_events": 40,
            "frozen_replay_drift": len(bear_diffs),
            "frozen_replay_differences": bear_diffs,
        },
        "stability": {
            "version": "daily20-prospective-stability-v1",
            "session": SESSION,
            "research_only": True, "production_writes": False,
            "strategy_promoted": False,
            "current_session_has_original_snapshot": not legacy,
            "frozen_snapshot_sha256": None if legacy else "a" * 64,
            "new_sealed_bull_signals": 0 if legacy else 20,
            "new_sealed_bear_signals": 0 if legacy else 40,
            "drift_threshold_percentage_points_exclusive": 1.0,
            "incidents_count": len(incidents) if legacy else 0,
            "incidents": incidents if legacy else [],
        },
        "finality": {
            "version": "daily20-source-finality-v1",
            "session": SESSION, "research_only": True,
            "research_hold": True, "verified": 0, "required": 26,
        },
        "hashes": {key + "_sha256": "a" * 64
                   for key in ("bull", "bear", "stability", "finality")},
    }


def run_fixture(**kwargs):
    return reconcile(SPEC, **fixture(**kwargs))


class ReplayReconciliationContractTests(unittest.TestCase):
    def test_20_bull_drift_and_four_material_legacy_incidents(self):
        r = run_fixture()
        self.assertEqual(r["bull_drift_count"], 20)
        self.assertEqual(r["bull_material_count"], 4)
        self.assertEqual(r["bear_drift_count"], 32)
        self.assertEqual(r["stability_incident_count"], 4)
        self.assertTrue(r["legacy_without_original_21_feature_snapshot"])
        self.assertTrue(r["legacy_bull_holds_reconciled"])
        self.assertFalse(r["original_journals_modified"])
        self.assertFalse(r["causal_upstream_mechanism_certified"])
        self.assertEqual(r["independent_source_finality_verified"], 0)
        self.assertEqual(len(r["observations"]), 52)

    def test_nonmaterial_bear_feature_change_is_not_bull_hold(self):
        r = run_fixture()
        bear = next(x for x in r["observations"] if x["family"] == "BEAR_RULE")
        self.assertEqual(bear["changed_fields"], ["rsi14"])
        self.assertFalse(bear["material_replay"])
        self.assertFalse(bear["stability_incident_present"])
        self.assertIsNone(bear["delta_percentage_points"])

    def test_single_missing_material_stability_incident_blocks_publication(self):
        reports = fixture()
        reports["stability"]["incidents"] = reports["stability"]["incidents"][:-1]
        reports["stability"]["incidents_count"] = 3
        with self.assertRaisesRegex(ValueError, "BULL_HOLD_RECONCILIATION_FAILED"):
            reconcile(SPEC, **reports)

    def test_wrong_legacy_candidate_flip_blocks_reconciliation(self):
        reports = fixture()
        reports["stability"]["incidents"][0]["candidate_flip"] = True
        with self.assertRaisesRegex(ValueError, "BULL_INCIDENT_VALUE_CONFLICT"):
            reconcile(SPEC, **reports)

    def test_spurious_material_bull_incident_rejected(self):
        reports = fixture()
        reports["stability"]["incidents"].append({
            "symbol": "QQQ", "family": "BULL_LOGISTIC",
            "candidate_flip": False, "probability_delta_pp": 0.05,
            "legacy_event_only_no_original_feature_snapshot": True,
            "research_hold": True,
        })
        reports["stability"]["incidents_count"] = 5
        with self.assertRaisesRegex(ValueError, "BULL_HOLD_RECONCILIATION_FAILED"):
            reconcile(SPEC, **reports)

    def test_cross_session_rejection(self):
        reports = fixture()
        reports["finality"]["session"] = "2026-11-19"
        with self.assertRaisesRegex(ValueError, "REPLAY_SESSION_MISMATCH"):
            reconcile(SPEC, **reports)

    def test_fake_finality_promotion_rejected(self):
        reports = fixture()
        reports["finality"]["verified"] = 26
        with self.assertRaisesRegex(ValueError, "REPLAY_TRADABILITY_OR_FINALITY_CLAIM"):
            reconcile(SPEC, **reports)

    def test_missing_original_feature_snapshot_not_fake_first_seal(self):
        reports = fixture()
        reports["stability"]["new_sealed_bull_signals"] = 20
        with self.assertRaisesRegex(ValueError, "REPLAY_STABILITY_ADMISSION_MISMATCH"):
            reconcile(SPEC, **reports)

    def test_genuinely_new_seal_without_drift_is_not_legacy(self):
        r = run_fixture(legacy=False, no_drift=True)
        self.assertFalse(r["legacy_without_original_21_feature_snapshot"])
        self.assertEqual(r["bull_drift_count"], 0)
        self.assertEqual(r["stability_incident_count"], 0)
        self.assertEqual(r["status"], "SNAPSHOT_ERA_REPLAY_TRIAGED_RESEARCH_HOLD")

    def test_frozen_event_sha_is_required(self):
        reports = fixture()
        reports["bull"]["frozen_replay_differences"][0]["frozen_event_hash"] = "invalid"
        with self.assertRaisesRegex(ValueError, "REPLAY_EVENT_HASH_INVALID"):
            reconcile(SPEC, **reports)

    def test_no_partially_sealed_journal(self):
        reports = fixture()
        reports["bull"]["signal_events"] = 19
        with self.assertRaisesRegex(ValueError, "REPLAY_PARTIAL_SEALED_UNIVERSE"):
            reconcile(SPEC, **reports)

    def test_deduplicate_bear_symbol_family(self):
        reports = fixture()
        reports["bear"]["frozen_replay_differences"][1] = deepcopy(
            reports["bear"]["frozen_replay_differences"][0])
        with self.assertRaisesRegex(ValueError, "REPLAY_DUPLICATED_EVENT"):
            reconcile(SPEC, **reports)

    def test_export_is_byte_stable_and_explicitly_unattributed(self):
        r = run_fixture()
        a, b = csv_bytes(r["observations"]), csv_bytes(r["observations"])
        self.assertEqual(a, b)
        self.assertEqual(len(a.decode().splitlines()), 53)
        self.assertIn("legacy_no_original_features", a.decode().splitlines()[0])
        self.assertTrue(all(not x["cause_certified"] for x in r["observations"]))

    def test_exact_one_pp_is_not_material(self):
        reports = fixture()
        r0 = reports["bull"]["frozen_replay_differences"][0]
        r0["recomputed_probability"] = r0["frozen_probability"] + 0.01
        if r0["symbol"] in IMPORTANT:
            reports["stability"]["incidents"] = [
                i for i in reports["stability"]["incidents"]
                if i["symbol"] != r0["symbol"]]
            reports["stability"]["incidents_count"] = len(
                reports["stability"]["incidents"])
        result = reconcile(SPEC, **reports)
        row = next(x for x in result["observations"]
                   if x["symbol"] == r0["symbol"] and x["family"] == "BULL_LOGISTIC")
        self.assertFalse(row["material_replay"])


if __name__ == "__main__":
    unittest.main()
