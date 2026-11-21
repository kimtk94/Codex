"""Offline tests for the research-only Daily20 provenance HOLD gate."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import stability_gate

from stability_gate import VERSION, classify


def snapshot(*, bull=.72, bear=.34, rule=False, feature="a" * 64):
    def model(p, candidate):
        return {"probability": p, "candidate": candidate}
    return {
        "schema": VERSION,
        "session": "2026-11-20",
        "models": {"SPY": {
            "ohlcv": {"close": 100.0},
            "feature_sha256": feature,
            "scored": {
                "BULL_LOGISTIC": model(bull, bull >= .7),
                "BEAR_LOGISTIC": model(bear, bear is not None and bear >= .7),
                "BEAR_RULE": model(None, rule),
            },
            "frozen_signal_hashes": {
                "BULL_LOGISTIC": "a" * 64,
                "BEAR_LOGISTIC": "b" * 64,
                "BEAR_RULE": "c" * 64,
            },
            "models": {
                "BULL_LOGISTIC": {
                    "training_hash": "train1", "fitted_model_hash": "coeff1"
                },
                "BEAR_LOGISTIC": {
                    "training_hash": "train2", "fitted_model_hash": "coeff2"
                },
            },
        }},
    }


class StabilityGateTests(unittest.TestCase):
    def test_identical_inputs_do_not_raise_hold(self):
        left = snapshot()
        rows, hold = classify(left, snapshot())
        self.assertEqual(rows, [])
        self.assertFalse(hold)

    def test_probability_change_over_one_percentage_point_holds(self):
        rows, hold = classify(snapshot(), snapshot(bull=.731))
        self.assertTrue(hold)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["family"], "BULL_LOGISTIC")
        self.assertAlmostEqual(rows[0]["probability_delta_pp"], 1.1)

    def test_one_pp_exact_not_hold(self):
        rows, hold = classify(snapshot(), snapshot(bull=.73))
        self.assertFalse(hold)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["research_hold"])

    def test_candidate_flip_holds_regardless_probability_magnitude(self):
        left, right = snapshot(rule=False), snapshot(rule=True)
        rows, hold = classify(left, right)
        self.assertTrue(hold)
        self.assertEqual(rows[0]["family"], "BEAR_RULE")
        self.assertTrue(rows[0]["candidate_flip"])

    def test_asof_feature_revision_below_threshold_is_advisory(self):
        rows, hold = classify(snapshot(), snapshot(feature="b" * 64))
        self.assertFalse(hold)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(x["asof_input_changed"] for x in rows))
        self.assertFalse(any(x["research_hold"] for x in rows))

    def test_missing_probability_is_hold(self):
        rows, hold = classify(snapshot(bear=.34), snapshot(bear=None))
        self.assertTrue(hold)
        self.assertTrue(rows[0]["probability_missing_changed"])


    def test_new_session_freezes_one_snapshot_and_preserves_future_immutability(self):
        spec = {"core": ["SPY"]}
        evidence = snapshot()
        evidence["models"]["SPY"]["scored"]["BULL_LOGISTIC"]["candidate"] = True
        bulls = {("2026-11-20", "SPY"):
                 {"candidate": True, "probability": .72, "hash": "a" * 64}}
        bears = {
            ("2026-11-20", "SPY", "BEAR_LOGISTIC"):
                {"candidate": False, "probability": .34, "hash": "b" * 64},
            ("2026-11-20", "SPY", "BEAR_RULE"):
                {"candidate": False, "probability": None, "hash": "c" * 64},
        }
        with TemporaryDirectory() as d:
            root = Path(d)
            prior = root / "prior.zip"
            prior.write_bytes(b"mock verified ZIP")
            (root / "bull.json").write_text(json.dumps({
                "last_completed_session": "2026-11-20", "new_signal_events": 20
            }))
            (root / "bear.json").write_text(json.dumps({
                "last_completed_session": "2026-11-20", "new_signal_events": 40
            }))
            with (patch.object(stability_gate, "_historical_snapshots", return_value={}),
                  patch.object(stability_gate, "read_score_rows", return_value={}),
                  patch.object(stability_gate, "_read_journal", return_value=[]),
                  patch.object(stability_gate, "check_events",
                               return_value=(bulls, set())),
                  patch.object(stability_gate, "validate_bear_events",
                               return_value=(bears, set())),
                  patch.object(stability_gate, "make_current_snapshot",
                               return_value=evidence)):
                report = stability_gate.run(
                    spec, prior, root, root, root / "scores.csv",
                    root / "bull.journal", root / "bear.journal",
                    root / "bull.json", root / "bear.json",
                    root / "stability")
            self.assertEqual(report["status"], "SEALED_NEW_SESSION")
            self.assertFalse(report["research_hold"])
            frozen = root / "stability/snapshots/2026-11-20.json"
            self.assertTrue(frozen.is_file())
            self.assertEqual(json.loads(frozen.read_text()), evidence)

    def test_same_session_drift_keeps_original_snapshot_bytes(self):
        spec = {"core": ["SPY"]}
        original = snapshot()
        current = snapshot(bull=.80)
        recorded = (json.dumps(original, separators=(",", ":")) + "\n").encode()
        bulls = {("2026-11-20", "SPY"):
                 {"candidate": True, "probability": .72, "hash": "a" * 64}}
        bears = {
            ("2026-11-20", "SPY", "BEAR_LOGISTIC"):
                {"candidate": False, "probability": .34, "hash": "b" * 64},
            ("2026-11-20", "SPY", "BEAR_RULE"):
                {"candidate": False, "probability": None, "hash": "c" * 64},
        }
        with TemporaryDirectory() as d:
            root = Path(d)
            prior = root / "prior.zip"
            prior.write_bytes(b"mock verified ZIP")
            (root / "bull.json").write_text(json.dumps({
                "last_completed_session": "2026-11-20", "new_signal_events": 0
            }))
            (root / "bear.json").write_text(json.dumps({
                "last_completed_session": "2026-11-20", "new_signal_events": 0
            }))
            with (patch.object(stability_gate, "_historical_snapshots",
                               return_value={"2026-11-20": recorded}),
                  patch.object(stability_gate, "read_score_rows", return_value={}),
                  patch.object(stability_gate, "_read_journal", return_value=[]),
                  patch.object(stability_gate, "check_events",
                               return_value=(bulls, set())),
                  patch.object(stability_gate, "validate_bear_events",
                               return_value=(bears, set())),
                  patch.object(stability_gate, "make_current_snapshot",
                               return_value=current)):
                report = stability_gate.run(
                    spec, prior, root, root, root / "scores.csv",
                    root / "bull.journal", root / "bear.journal",
                    root / "bull.json", root / "bear.json",
                    root / "stability")
            self.assertEqual(report["status"], "REPLAY_DRIFT_RESEARCH_HOLD")
            self.assertTrue(report["research_hold"])
            self.assertFalse(report["promotional_attribution_allowed"])
            self.assertEqual((root / "stability/snapshots/2026-11-20.json").read_bytes(),
                             recorded)


if __name__ == "__main__":
    unittest.main()
